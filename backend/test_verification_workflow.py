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
from datetime import datetime, timezone

# Use an isolated SQLite file so tests never touch the demo DB. Must be set
# before importing database/main (engine is created at import time).
os.environ["DATABASE_URL"] = "sqlite:///./test_verification_workflow.db"

from fastapi.testclient import TestClient

from database import init_db
from auth import seed_demo_users
import main
from verification_service import sync_auto_tasks


def check(name: str, condition: bool, info: str = ""):
    if condition:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f": {info}" if info else ""))
        sys.exit(1)


def _new_task(client, headers) -> str:
    """Create a fresh verification task and return its task_id."""
    resp = client.post(
        "/api/verification-tokens",
        params={"plant_id": "plant-a"},
        headers=headers,
        json={"sensor_id": "LT-5100", "verification_type": "field_check", "valid_minutes": 30, "note": "demo"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["task_id"]


def _transition(client, task_id, state, headers, actor=None, actor_role=None, evidence_note="", evidence=None):
    return client.post(
        "/api/verification-tasks/state",
        params={"plant_id": "plant-a"},
        headers=headers,
        json={
            "task_id": task_id,
            "state": state,
            "actor": actor,
            "actor_role": actor_role,
            "evidence_note": evidence_note,
            "evidence": evidence,
        },
    )


def _complete_evidence_payload():
    return {
        "technician_note": "Local field verification completed with required checklist evidence.",
        "method": "field_check",
        "evidence_items": [
            {"id": "local_reading_value", "label": "Local reading value", "value": 52.0},
            {"id": "local_reading_unit", "label": "Local reading unit", "value": "ft"},
            {"id": "dcs_reading_at_same_time", "label": "DCS reading at same time", "value": 51.5},
            {"id": "discrepancy_local_dcs", "label": "Discrepancy (local - DCS)", "value": 0.5},
            {"id": "physical_condition_note", "label": "Physical condition note", "value": "No blockage or visible damage observed."},
        ],
    }


def test_full_lifecycle_and_audit(client, auth_headers):
    task_id = _new_task(client, auth_headers("Engineer"))

    r1 = _transition(client, task_id, "ASSIGNED", auth_headers("Maintenance"), actor="tech.morgan", actor_role="Maintenance")
    check("ASSIGNED returns 200", r1.status_code == 200, r1.text)
    check("ASSIGNED records authenticated owner", r1.json()["task"].get("assigned_to") == "maint")

    r2 = _transition(client, task_id, "FIELD_CHECK_DONE", auth_headers("Maintenance"), actor="tech.morgan", actor_role="Maintenance",
                     evidence_note="Local sight glass reads 52 ft, matches DCS within 1 ft.",
                     evidence=_complete_evidence_payload())
    check("FIELD_CHECK_DONE returns 200", r2.status_code == 200, r2.text)
    check("FIELD_CHECK_DONE records authenticated checker", r2.json()["task"].get("field_checked_by") == "maint")

    r3 = _transition(client, task_id, "ACCEPTED", auth_headers("Engineer"), actor="eng.lee", actor_role="Engineer",
                     evidence_note="Field evidence consistent; accepting verification.")
    check("ACCEPTED returns 200", r3.status_code == 200, r3.text)
    check("ACCEPTED records authenticated acceptor", r3.json()["task"].get("accepted_by") == "engineer")
    check("ACCEPTED clears handover requirement", r3.json()["task"].get("handover_required") is False)

    # Audit trail: creation (REQUESTED) + 3 transitions = 4 ordered immutable events.
    audit = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": task_id})
    check("audit returns 200", audit.status_code == 200, audit.text)
    events = audit.json()["events"]
    check("audit has 4 events", len(events) == 4, f"got {len(events)}: {[e['to_state'] for e in events]}")
    states = [e["to_state"] for e in events]
    check("audit ordered REQUESTED->ASSIGNED->FIELD_CHECK_DONE->ACCEPTED",
          states == ["REQUESTED", "ASSIGNED", "FIELD_CHECK_DONE", "ACCEPTED"], f"got {states}")
    check("audit captures authenticated actor on ACCEPTED", events[-1]["actor"] == "engineer")
    check("audit captures evidence note on FIELD_CHECK_DONE", bool(events[2]["evidence_note"]))
    check("audit captures from_state on transition", events[1]["from_state"] == "REQUESTED")


def test_illegal_transition_rejected(client, auth_headers):
    task_id = _new_task(client, auth_headers("Engineer"))
    # REQUESTED -> FIELD_CHECK_DONE is illegal (must go through ASSIGNED)
    r = _transition(client, task_id, "FIELD_CHECK_DONE", auth_headers("Maintenance"), actor="tech", actor_role="Maintenance",
                    evidence_note="skipping ahead", evidence=_complete_evidence_payload())
    check("illegal jump REQUESTED->FIELD_CHECK_DONE returns 400", r.status_code == 400, r.text)


def test_evidence_note_required(client, auth_headers):
    task_id = _new_task(client, auth_headers("Engineer"))
    _transition(client, task_id, "ASSIGNED", auth_headers("Maintenance"), actor="tech", actor_role="Maintenance")
    # FIELD_CHECK_DONE without evidence note
    r = _transition(client, task_id, "FIELD_CHECK_DONE", auth_headers("Maintenance"), actor="tech", actor_role="Maintenance", evidence_note="")
    check("FIELD_CHECK_DONE without evidence returns 422", r.status_code == 422, r.text)


def test_structured_evidence_items_required(client, auth_headers):
    task_id = _new_task(client, auth_headers("Engineer"))
    _transition(client, task_id, "ASSIGNED", auth_headers("Maintenance"), actor="tech", actor_role="Maintenance")
    r = _transition(
        client,
        task_id,
        "FIELD_CHECK_DONE",
        auth_headers("Maintenance"),
        actor="tech",
        actor_role="Maintenance",
        evidence_note="Note alone is not enough.",
        evidence={"technician_note": "Note alone is not enough.", "evidence_items": []},
    )
    check("FIELD_CHECK_DONE without structured checklist returns 422", r.status_code == 422, r.text)
    detail = r.json().get("detail", {})
    check("missing evidence ids returned", bool(detail.get("missing_evidence_item_ids")), str(detail))


def test_role_scope_enforced(client, auth_headers):
    task_id = _new_task(client, auth_headers("Engineer"))
    _transition(client, task_id, "ASSIGNED", auth_headers("Maintenance"), actor="tech", actor_role="Maintenance")
    _transition(client, task_id, "FIELD_CHECK_DONE", auth_headers("Maintenance"), actor="tech", actor_role="Maintenance",
                evidence_note="checked", evidence=_complete_evidence_payload())
    # Operator may not ACCEPT (only Engineer/Manager)
    r = _transition(client, task_id, "ACCEPTED", auth_headers("Operator"), actor="op.kim", actor_role="Operator", evidence_note="ok")
    check("Operator accepting returns 403", r.status_code == 403, r.text)


def test_audit_is_append_only_across_tasks(client, auth_headers):
    # Two tasks → audit filtered by task returns only that task's trail.
    t1 = _new_task(client, auth_headers("Engineer"))
    t2 = _new_task(client, auth_headers("Engineer"))
    _transition(client, t1, "ASSIGNED", auth_headers("Maintenance"), actor="a", actor_role="Maintenance")
    a1 = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": t1}).json()
    a2 = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": t2}).json()
    check("task1 audit isolated (2 events)", a1["count"] == 2, f"got {a1['count']}")
    check("task2 audit isolated (1 event)", a2["count"] == 1, f"got {a2['count']}")


def test_fake_sensor_rejected(client, auth_headers):
    resp = client.post(
        "/api/verification-tokens",
        params={"plant_id": "plant-a"},
        headers=auth_headers("Engineer"),
        json={"sensor_id": "FAKE-SENSOR-999", "verification_type": "field_check", "valid_minutes": 30, "note": "bad"},
    )
    check("fake sensor verification task rejected", resp.status_code == 422, resp.text)


def test_auto_task_creation_is_audited(client):
    db = next(main.get_db())
    try:
        tasks = sync_auto_tasks(
            db,
            plant_id="plant-a",
            incidents=[],
            confidence=[{
                "sensor_id": "PT-3100",
                "tier": "LOW",
                "trust_state": "QUARANTINED",
                "decision_basis_allowed": False,
            }],
            plant_context={"state": "MANUAL_VERIFICATION_REQUIRED"},
            now=1_700_000_000,
        )
    finally:
        db.close()
    task_id = next(item["task_id"] for item in tasks if item["sensor_id"] == "PT-3100")
    audit = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": task_id})
    states = [event["to_state"] for event in audit.json()["events"]]
    check("auto task REQUESTED event audited", states == ["REQUESTED"], f"got {states}")


def test_expiration_is_audited(client, auth_headers):
    resp = client.post(
        "/api/verification-tokens",
        params={"plant_id": "plant-a"},
        headers=auth_headers("Engineer"),
        json={"sensor_id": "FI-2010", "verification_type": "field_check", "valid_minutes": 1, "note": "expires"},
    )
    task_id = resp.json()["task_id"]
    db = next(main.get_db())
    try:
        from database import VerificationTask
        task = db.query(VerificationTask).filter(VerificationTask.task_id == task_id).one()
        task.valid_until = datetime.fromtimestamp(0, timezone.utc).replace(tzinfo=None)
        db.commit()
    finally:
        db.close()
    client.get("/api/verification-tokens", params={"plant_id": "plant-a", "active_only": False})
    audit = client.get("/api/verification-tasks/audit", params={"plant_id": "plant-a", "task_id": task_id})
    states = [event["to_state"] for event in audit.json()["events"]]
    check("expiration event audited", states[-1] == "EXPIRED", f"got {states}")


def run_all():
    init_db()
    seed_demo_users()
    # No context manager → lifespan (and background tick loops) do not start.
    client = TestClient(main.app)
    credentials = {
        "Operator": ("operator", "ConfidenceOS-Op-2025"),
        "Maintenance": ("maint", "ConfidenceOS-Maint-2025"),
        "Engineer": ("engineer", "ConfidenceOS-Eng-2025"),
        "Manager": ("manager", "ConfidenceOS-Mgr-2025"),
    }
    headers_by_role = {}
    for role, (username, password) in credentials.items():
        login = client.post("/api/auth/login", data={"username": username, "password": password})
        headers_by_role[role] = {"Authorization": f"Bearer {login.json()['access_token']}"}

    print("\n-- Full lifecycle + immutable audit trail ---------------")
    class Headers:
        def __call__(self, role):
            return headers_by_role[role]

    test_full_lifecycle_and_audit(client, Headers())

    print("\n-- Illegal transition guard -----------------------------")
    test_illegal_transition_rejected(client, Headers())

    print("\n-- Evidence note enforcement ----------------------------")
    test_evidence_note_required(client, Headers())
    test_structured_evidence_items_required(client, Headers())

    print("\n-- Advisory role scoping --------------------------------")
    test_role_scope_enforced(client, Headers())

    print("\n-- Audit trail isolation by task ------------------------")
    test_audit_is_append_only_across_tasks(client, Headers())

    print("\n-- Sensor validation ------------------------------------")
    test_fake_sensor_rejected(client, Headers())

    print("\n-- Auto task and expiry audit coverage ------------------")
    test_auto_task_creation_is_audited(client)
    test_expiration_is_audited(client, Headers())

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
