"""
test_verification_workflow.py — Tests for the real field-verification workflow (R2-B).

Covers the guarded state machine, evidence enforcement, role scoping, immutable
audit trail, and handover-debt clearing. ConfidenceOS stays read-only — this
workflow only logs engineering verification, never a control action.

Run from backend directory:
    python test_verification_workflow.py
"""

import os
import sys

# Use an isolated SQLite file so tests never touch the demo DB. Must be set
# before importing database/main (engine is created at import time).
os.environ["DATABASE_URL"] = "sqlite:///./test_verification_workflow.db"

from fastapi.testclient import TestClient

from database import init_db
import main


def check(name: str, condition: bool, info: str = ""):
    if condition:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f": {info}" if info else ""))
        sys.exit(1)


def _new_task(client) -> str:
    """Create a fresh verification task and return its task_id."""
    resp = client.post(
        "/api/verification-tokens",
        params={"plant_id": "plant-a"},
        json={"sensor_id": "LT-5100", "verification_type": "field_check", "valid_minutes": 30, "note": "demo"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["task_id"]


def _transition(client, task_id, state, actor=None, actor_role=None, evidence_note=""):
    return client.post(
        "/api/verification-tasks/state",
        params={"plant_id": "plant-a"},
        json={
            "task_id": task_id,
            "state": state,
            "actor": actor,
            "actor_role": actor_role,
            "evidence_note": evidence_note,
        },
    )


def test_full_lifecycle_and_audit(client):
    task_id = _new_task(client)

    r1 = _transition(client, task_id, "ASSIGNED", actor="tech.morgan", actor_role="Maintenance")
    check("ASSIGNED returns 200", r1.status_code == 200, r1.text)
    check("ASSIGNED records owner", r1.json()["task"].get("assigned_to") == "tech.morgan")

    r2 = _transition(client, task_id, "FIELD_CHECK_DONE", actor="tech.morgan", actor_role="Maintenance",
                     evidence_note="Local sight glass reads 52 ft, matches DCS within 1 ft.")
    check("FIELD_CHECK_DONE returns 200", r2.status_code == 200, r2.text)
    check("FIELD_CHECK_DONE records checker", r2.json()["task"].get("field_checked_by") == "tech.morgan")

    r3 = _transition(client, task_id, "ACCEPTED", actor="eng.lee", actor_role="Engineer",
                     evidence_note="Field evidence consistent; accepting verification.")
    check("ACCEPTED returns 200", r3.status_code == 200, r3.text)
    check("ACCEPTED records acceptor", r3.json()["task"].get("accepted_by") == "eng.lee")
    check("ACCEPTED clears handover requirement", r3.json()["task"].get("handover_required") is False)

    # Audit trail: creation (REQUESTED) + 3 transitions = 4 ordered immutable events.
    audit = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": task_id})
    check("audit returns 200", audit.status_code == 200, audit.text)
    events = audit.json()["events"]
    check("audit has 4 events", len(events) == 4, f"got {len(events)}: {[e['to_state'] for e in events]}")
    states = [e["to_state"] for e in events]
    check("audit ordered REQUESTED->ASSIGNED->FIELD_CHECK_DONE->ACCEPTED",
          states == ["REQUESTED", "ASSIGNED", "FIELD_CHECK_DONE", "ACCEPTED"], f"got {states}")
    check("audit captures actor on ACCEPTED", events[-1]["actor"] == "eng.lee")
    check("audit captures evidence note on FIELD_CHECK_DONE", bool(events[2]["evidence_note"]))
    check("audit captures from_state on transition", events[1]["from_state"] == "REQUESTED")


def test_illegal_transition_rejected(client):
    task_id = _new_task(client)
    # REQUESTED -> FIELD_CHECK_DONE is illegal (must go through ASSIGNED)
    r = _transition(client, task_id, "FIELD_CHECK_DONE", actor="tech", actor_role="Maintenance",
                    evidence_note="skipping ahead")
    check("illegal jump REQUESTED->FIELD_CHECK_DONE returns 400", r.status_code == 400, r.text)


def test_evidence_note_required(client):
    task_id = _new_task(client)
    _transition(client, task_id, "ASSIGNED", actor="tech", actor_role="Maintenance")
    # FIELD_CHECK_DONE without evidence note
    r = _transition(client, task_id, "FIELD_CHECK_DONE", actor="tech", actor_role="Maintenance", evidence_note="")
    check("FIELD_CHECK_DONE without evidence returns 422", r.status_code == 422, r.text)


def test_role_scope_enforced(client):
    task_id = _new_task(client)
    _transition(client, task_id, "ASSIGNED", actor="tech", actor_role="Maintenance")
    _transition(client, task_id, "FIELD_CHECK_DONE", actor="tech", actor_role="Maintenance",
                evidence_note="checked")
    # Operator may not ACCEPT (only Engineer/Manager)
    r = _transition(client, task_id, "ACCEPTED", actor="op.kim", actor_role="Operator", evidence_note="ok")
    check("Operator accepting returns 403", r.status_code == 403, r.text)


def test_audit_is_append_only_across_tasks(client):
    # Two tasks → audit filtered by task returns only that task's trail.
    t1 = _new_task(client)
    t2 = _new_task(client)
    _transition(client, t1, "ASSIGNED", actor="a", actor_role="Maintenance")
    a1 = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": t1}).json()
    a2 = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": t2}).json()
    check("task1 audit isolated (2 events)", a1["count"] == 2, f"got {a1['count']}")
    check("task2 audit isolated (1 event)", a2["count"] == 1, f"got {a2['count']}")


def run_all():
    init_db()
    # No context manager → lifespan (and background tick loops) do not start.
    client = TestClient(main.app)

    print("\n-- Full lifecycle + immutable audit trail ---------------")
    test_full_lifecycle_and_audit(client)

    print("\n-- Illegal transition guard -----------------------------")
    test_illegal_transition_rejected(client)

    print("\n-- Evidence note enforcement ----------------------------")
    test_evidence_note_required(client)

    print("\n-- Advisory role scoping --------------------------------")
    test_role_scope_enforced(client)

    print("\n-- Audit trail isolation by task ------------------------")
    test_audit_is_append_only_across_tasks(client)

    print("\nAll verification-workflow tests passed.\n")


def _cleanup():
    for suffix in ("", "-journal"):
        path = f"./test_verification_workflow.db{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    try:
        run_all()
    finally:
        _cleanup()
