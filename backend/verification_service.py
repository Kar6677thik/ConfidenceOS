"""
verification_service.py - Durable field-verification workflow.

The service keeps the legacy token-shaped API responses while making task
state durable and auditable in SQLite. It never changes confidence and never
writes process controls.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from asset_model import sensor_by_tag
from database import VerificationEvidence, VerificationTask, log_verification_event

logger = logging.getLogger(__name__)

# ── CMMS webhook stub ─────────────────────────────────────────────────────────
# Set CONFIDENCEOS_CMMS_WEBHOOK_URL to fire a POST on every verification state
# change. The payload matches the task_to_dict schema so CMMS can create or
# close work orders from the event stream.

_CMMS_WEBHOOK_URL: str | None = os.getenv("CONFIDENCEOS_CMMS_WEBHOOK_URL")


def _fire_cmms_webhook(task_dict: dict, event: str) -> None:
    """
    POST verification task state to the configured CMMS webhook.
    Non-blocking: logs failures but never raises — a CMMS outage must not
    block the verification workflow.
    """
    if not _CMMS_WEBHOOK_URL:
        return
    try:
        import urllib.request
        payload = json.dumps({
            "event": event,
            "task": task_dict,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }).encode()
        req = urllib.request.Request(
            _CMMS_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            logger.info("CMMS webhook fired: event=%s status=%s", event, resp.status)
    except Exception as exc:
        logger.warning("CMMS webhook failed (non-fatal): %s", exc)


TERMINAL_STATES = {"ACCEPTED", "EXPIRED"}
VERIFICATION_TRANSITIONS = {
    "REQUESTED": {"ASSIGNED", "EXPIRED"},
    "ASSIGNED": {"FIELD_CHECK_DONE", "EXPIRED"},
    "FIELD_CHECK_DONE": {"ACCEPTED", "REJECTED", "EXPIRED"},
    "REJECTED": {"ASSIGNED", "EXPIRED"},
    "ACCEPTED": set(),
    "EXPIRED": set(),
}
VERIFICATION_EVIDENCE_REQUIRED = {"FIELD_CHECK_DONE", "ACCEPTED", "REJECTED"}
VERIFICATION_ROLE_SCOPE = {
    "ASSIGNED": {"Maintenance", "Engineer", "Manager"},
    "FIELD_CHECK_DONE": {"Maintenance", "Engineer"},
    "ACCEPTED": {"Engineer", "Manager"},
    "REJECTED": {"Engineer", "Manager"},
    "EXPIRED": {"Operator", "Maintenance", "Engineer", "Manager", "Auditor", "ConfidenceOS"},
}
METHODS_BY_SENSOR_TYPE = {
    "level": {"field_check", "local_field_check", "manual_level_verification", "sight_glass"},
    "flow_in": {"field_check", "local_field_check", "manual_flow_verification"},
    "flow_out": {"field_check", "local_field_check", "manual_flow_verification"},
    "pressure": {"field_check", "local_field_check", "manual_pressure_verification"},
    "temperature": {"field_check", "local_field_check", "manual_temperature_verification"},
    "valve": {"field_check", "local_field_check", "position_check"},
    "vibration": {"field_check", "local_field_check", "vibration_check"},
}
DEFAULT_EVIDENCE_REQUIRED = ["local indication", "field note", "time-stamped confirmation"]

# Procedure links: reference documents per verification method (ISA-S5.4 / site SOP pointers)
PROCEDURE_LINKS: dict[str, str] = {
    "field_check":                    "SOP-INST-001: General Instrument Field Check Procedure",
    "local_field_check":              "SOP-INST-001: General Instrument Field Check Procedure",
    "manual_level_verification":      "SOP-INST-010: Level Transmitter Verification (Sight Glass Method)",
    "sight_glass":                    "SOP-INST-010: Level Transmitter Verification (Sight Glass Method)",
    "manual_flow_verification":       "SOP-INST-020: Flow Meter Field Verification Procedure",
    "manual_pressure_verification":   "SOP-INST-030: Pressure Transmitter Loop Check Procedure",
    "manual_temperature_verification":"SOP-INST-040: Temperature Element Verification Procedure",
    "position_check":                 "SOP-INST-050: Valve Position Indicator Check Procedure",
    "vibration_check":                "SOP-INST-060: Vibration Sensor Field Check Procedure",
}


def create_task(
    db: Session,
    *,
    plant_id: str,
    sensor_id: str,
    verification_type: str = "field_check",
    valid_minutes: float = 30.0,
    note: str = "",
    source: str = "manual",
    actor: str | None = None,
    actor_role: str | None = None,
    task_id: str | None = None,
    commit: bool = True,
    # CMMS / permit-to-work fields (optional)
    cmms_work_order: str | None = None,
    permit_to_work_ref: str | None = None,
    asset_tag_number: str | None = None,
    loop_number: str | None = None,
    field_location: str | None = None,
) -> dict:
    """Create a durable verification task and REQUESTED audit event."""
    sensor = _validate_sensor(sensor_id)
    method = _validate_method(sensor, verification_type)
    now = _utcnow()
    valid_minutes = max(1.0, min(float(valid_minutes or 30.0), 240.0))
    valid_until = now + timedelta(minutes=valid_minutes)
    if not task_id:
        uniq = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        task_id = f"verification-task:{sensor_id}:{uniq}"

    existing = db.query(VerificationTask).filter(VerificationTask.task_id == task_id).one_or_none()
    if existing and existing.state not in TERMINAL_STATES:
        return task_to_dict(existing)
    if existing and existing.state in TERMINAL_STATES:
        task_id = f"{task_id}:{int(time.time())}-{uuid.uuid4().hex[:6]}"

    task = VerificationTask(
        plant_id=plant_id,
        task_id=task_id,
        token_id=f"{plant_id}:{sensor_id}:{task_id.split(':')[-1]}",
        sensor_id=sensor_id,
        state="REQUESTED",
        source=source,
        assigned_role="Maintenance",
        verification_method=method,
        verification_type=method,
        evidence_required_json=json.dumps(DEFAULT_EVIDENCE_REQUIRED),
        note=note,
        valid_until=valid_until,
        created_at=now,
        updated_at=now,
        handover_required=1,
        active=1,
        closeout_status="open",
        confidence_override=0,
        usable_as_reference=0,
        cmms_work_order=cmms_work_order,
        permit_to_work_ref=permit_to_work_ref,
        asset_tag_number=asset_tag_number,
        loop_number=loop_number,
        field_location=field_location,
    )
    try:
        db.add(task)
        log_verification_event(
            db,
            plant_id=plant_id,
            task_id=task.task_id,
            to_state="REQUESTED",
            from_state=None,
            sensor_id=sensor_id,
            actor=actor,
            actor_role=actor_role,
            evidence_note=note or ("Auto-generated verification requested." if source == "auto" else "Verification requested."),
            commit=False,
        )
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        raise
    result = task_to_dict(task)
    _fire_cmms_webhook(result, event="verification_task.requested")
    return result


def sync_auto_tasks(
    db: Session,
    *,
    plant_id: str,
    incidents: list[dict],
    confidence: list[dict],
    plant_context: dict | None,
    now: float | None = None,
    commit: bool = True,
) -> list[dict]:
    """Create requested auto tasks and audit expiry for due tasks."""
    current = _datetime_from_ts(now) if now else _utcnow()
    expire_due_tasks(db, plant_id=plant_id, current=current, commit=commit)
    requested = _requested_sensors(incidents, confidence, plant_context)
    for sensor_id in sorted(requested):
        try:
            _validate_sensor(sensor_id)
        except HTTPException:
            continue
        existing = _active_task_for_sensor(db, plant_id, sensor_id)
        if existing:
            continue
        create_task(
            db,
            plant_id=plant_id,
            sensor_id=sensor_id,
            verification_type="local_field_check",
            valid_minutes=30.0,
            note="Generated because trust quarantine or handover block requires field verification.",
            source="auto",
            actor="ConfidenceOS",
            actor_role="ConfidenceOS",
            task_id=f"verification-task:{sensor_id}",
            commit=commit,
        )
    return list_tasks(db, plant_id=plant_id, include_closed=True, expire=False)


def transition_task(
    db: Session,
    *,
    plant_id: str,
    task_id: str,
    to_state: str,
    actor: str | None,
    actor_role: str | None,
    evidence_note: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict:
    """Move a task through the guarded lifecycle in one DB transaction."""
    state = (to_state or "").upper()
    if state not in VERIFICATION_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"state must be one of {sorted(VERIFICATION_TRANSITIONS)}")

    actor_role = actor_role or None
    allowed_roles = VERIFICATION_ROLE_SCOPE.get(state)
    if allowed_roles and actor_role and actor_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{actor_role}' may not perform transition to {state}. Allowed: {sorted(allowed_roles)}",
        )

    task = _task_by_id(db, plant_id, task_id)
    current_state = task.state
    legal = VERIFICATION_TRANSITIONS.get(current_state, set())
    if state != current_state and state not in legal:
        raise HTTPException(
            status_code=400,
            detail=f"Illegal transition {current_state} -> {state}. Legal next states: {sorted(legal)}",
        )

    evidence_payload = dict(evidence or {})
    note = (evidence_note or evidence_payload.get("technician_note") or "").strip()
    if state in VERIFICATION_EVIDENCE_REQUIRED and not note:
        raise HTTPException(status_code=422, detail=f"An evidence note is required to move a task to {state}.")

    now = _utcnow()
    try:
        _apply_state(task, state, actor, now, note)
        if state in VERIFICATION_EVIDENCE_REQUIRED or evidence_payload:
            db.add(_evidence_row(task, state, actor, note, evidence_payload, now))
        log_verification_event(
            db,
            plant_id=plant_id,
            task_id=task.task_id,
            to_state=state,
            from_state=current_state,
            sensor_id=task.sensor_id,
            actor=actor,
            actor_role=actor_role,
            evidence_note=note or None,
            commit=False,
        )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    result = task_to_dict(task)
    _fire_cmms_webhook(result, event=f"verification_task.{state.lower()}")
    return result


def expire_due_tasks(db: Session, *, plant_id: str, current: datetime | None = None, commit: bool = True) -> list[dict]:
    """Expire overdue active tasks and write one audit event per expiration."""
    current = current or _utcnow()
    expired = []
    due = (
        db.query(VerificationTask)
        .filter(
            VerificationTask.plant_id == plant_id,
            VerificationTask.active == 1,
            VerificationTask.valid_until <= current,
            VerificationTask.state.notin_(list(TERMINAL_STATES)),
        )
        .all()
    )
    if not due:
        return []
    try:
        for task in due:
            from_state = task.state
            _apply_state(task, "EXPIRED", "ConfidenceOS", current, "Task expired before acceptance.")
            log_verification_event(
                db,
                plant_id=plant_id,
                task_id=task.task_id,
                to_state="EXPIRED",
                from_state=from_state,
                sensor_id=task.sensor_id,
                actor="ConfidenceOS",
                actor_role="ConfidenceOS",
                evidence_note="Task expired before acceptance.",
                commit=False,
            )
            expired.append(task_to_dict(task))
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return expired


def list_tasks(
    db: Session,
    *,
    plant_id: str,
    active_only: bool = False,
    include_closed: bool = True,
    expire: bool = True,
    limit: int = 200,
) -> list[dict]:
    if expire:
        expire_due_tasks(db, plant_id=plant_id)
    query = db.query(VerificationTask).filter(VerificationTask.plant_id == plant_id)
    if active_only:
        query = query.filter(VerificationTask.active == 1)
    elif not include_closed:
        query = query.filter(VerificationTask.state.notin_(list(TERMINAL_STATES)))
    rows = query.order_by(VerificationTask.updated_at.desc(), VerificationTask.created_at.desc()).limit(limit).all()
    return [task_to_dict(row) for row in rows]


def task_to_dict(task: VerificationTask) -> dict:
    evidence_required = _loads_list(task.evidence_required_json) or DEFAULT_EVIDENCE_REQUIRED
    active = bool(task.active) and task.state not in TERMINAL_STATES and task.valid_until > _utcnow()
    return {
        "task_id": task.task_id,
        "token_id": task.token_id or task.task_id,
        "plant_id": task.plant_id,
        "sensor_id": task.sensor_id,
        "state": task.state,
        "source": task.source,
        "assigned_role": task.assigned_role,
        "assigned_to": task.assigned_to,
        "assigned_at": _iso(task.assigned_at),
        "field_checked_by": task.field_checked_by,
        "field_checked_at": _iso(task.field_checked_at),
        "accepted_by": task.accepted_by,
        "accepted_at": _iso(task.accepted_at),
        "rejected_by": task.rejected_by,
        "rejected_at": _iso(task.rejected_at),
        "verification_method": task.verification_method,
        "verification_type": task.verification_type,
        "evidence_required": evidence_required,
        "last_evidence_summary": task.last_evidence_summary,
        "note": task.note,
        "created_at": _timestamp(task.created_at),
        "created_at_iso": _iso(task.created_at),
        "valid_until": _timestamp(task.valid_until),
        "valid_until_iso": _iso(task.valid_until),
        "updated_at": _timestamp(task.updated_at),
        "updated_at_iso": _iso(task.updated_at),
        "handover_required": bool(task.handover_required),
        "active": active,
        "expired": task.state == "EXPIRED" or task.valid_until <= _utcnow(),
        "closeout_status": task.closeout_status,
        "confidence_override": False,
        "usable_as_reference": bool(task.usable_as_reference),
        # CMMS / permit-to-work integration
        "cmms_work_order": task.cmms_work_order,
        "permit_to_work_ref": task.permit_to_work_ref,
        "asset_tag_number": task.asset_tag_number,
        "loop_number": task.loop_number,
        "field_location": task.field_location,
        # Procedure link (ISA-S5.4 / site SOP reference)
        "procedure_ref": PROCEDURE_LINKS.get(task.verification_method, PROCEDURE_LINKS["field_check"]),
    }


def _requested_sensors(incidents: list[dict], confidence: list[dict], plant_context: dict | None) -> set[str]:
    requested = set()
    context_state = (plant_context or {}).get("state")
    handover_blocked = any(
        "accept_handover_without_verification" in (incident.get("action_contract") or {}).get("blocked_decisions", [])
        for incident in incidents or []
    )
    for item in confidence or []:
        if item.get("trust_state") == "QUARANTINED" or (
            item.get("tier") in ("LOW", "CRITICAL") and item.get("decision_basis_allowed") is False
        ):
            if item.get("sensor_id"):
                requested.add(item["sensor_id"])
    if context_state == "MANUAL_VERIFICATION_REQUIRED" or handover_blocked:
        for incident in incidents or []:
            for sensor_id in incident.get("affected_sensors", []):
                if sensor_id:
                    requested.add(sensor_id)
    return requested


def _active_task_for_sensor(db: Session, plant_id: str, sensor_id: str) -> VerificationTask | None:
    return (
        db.query(VerificationTask)
        .filter(
            VerificationTask.plant_id == plant_id,
            VerificationTask.sensor_id == sensor_id,
            VerificationTask.active == 1,
            VerificationTask.state.notin_(list(TERMINAL_STATES)),
        )
        .order_by(VerificationTask.created_at.desc())
        .first()
    )


def _task_by_id(db: Session, plant_id: str, task_id: str) -> VerificationTask:
    task = (
        db.query(VerificationTask)
        .filter(VerificationTask.plant_id == plant_id)
        .filter((VerificationTask.task_id == task_id) | (VerificationTask.token_id == task_id))
        .one_or_none()
    )
    if not task:
        raise HTTPException(status_code=404, detail=f"No verification task '{task_id}'")
    return task


def _apply_state(task: VerificationTask, state: str, actor: str | None, now: datetime, note: str | None) -> None:
    task.state = state
    task.updated_at = now
    if note:
        task.note = note
        task.last_evidence_summary = note
    if state == "ASSIGNED":
        task.assigned_to = actor
        task.assigned_at = now
    elif state == "FIELD_CHECK_DONE":
        task.field_checked_by = actor
        task.field_checked_at = now
    elif state == "ACCEPTED":
        task.accepted_by = actor
        task.accepted_at = now
    elif state == "REJECTED":
        task.rejected_by = actor
        task.rejected_at = now
    task.handover_required = 0 if state in TERMINAL_STATES else 1
    task.active = 0 if state in TERMINAL_STATES else 1
    task.closeout_status = "accepted" if state == "ACCEPTED" else "expired" if state == "EXPIRED" else "open"


def _evidence_row(task: VerificationTask, state: str, actor: str | None, note: str, evidence: dict[str, Any], now: datetime) -> VerificationEvidence:
    value = evidence.get("field_reading_value")
    try:
        value = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    return VerificationEvidence(
        plant_id=task.plant_id,
        task_id=task.task_id,
        sensor_id=task.sensor_id,
        state=state,
        method=evidence.get("method") or task.verification_method,
        field_reading_value=value,
        field_reading_unit=evidence.get("field_reading_unit"),
        technician_note=evidence.get("technician_note") or note,
        attachment_ref=evidence.get("attachment_ref"),
        captured_by=actor,
        accepted_by=actor if state == "ACCEPTED" else None,
        captured_at=now,
        evidence_json=json.dumps(evidence or {}),
    )


def _validate_sensor(sensor_id: str) -> dict:
    sensor = sensor_by_tag(sensor_id)
    if not sensor:
        sensor = _metadata_only_sensor(sensor_id)
    if not sensor:
        raise HTTPException(status_code=422, detail=f"Unknown sensor_id '{sensor_id}' for active asset model or live tag family.")
    return sensor


def _metadata_only_sensor(sensor_id: str) -> dict:
    """Return a controlled verification profile for live tags outside the active model.

    Studio can switch the global asset model while the simulator is still
    streaming another plant. Verification must remain available for valid live
    tags, but we still reject arbitrary strings. This classifier only accepts
    common industrial tag families already used by the demo/simulator.
    """
    tag = str(sensor_id or "").strip().upper()
    normalized = tag.replace("_", "-").replace(".", "-")
    prefix = normalized.split("-", 1)[0]
    compact = "".join(ch for ch in tag if ch.isalnum())
    candidates = [
        (("LT", "LIT"), "level"),
        (("FI", "FIT"), "flow_in"),
        (("FO",), "flow_out"),
        (("PT",), "pressure"),
        (("TT", "TEMP"), "temperature"),
        (("ZT",), "valve"),
        (("VIB",), "vibration"),
    ]
    for prefixes, sensor_type in candidates:
        if prefix in prefixes or any(compact.startswith(item) for item in prefixes):
            if any(ch.isdigit() for ch in compact):
                return {
                    "tag": sensor_id,
                    "sensor_type": sensor_type,
                    "role": sensor_type,
                    "source": "metadata_only_live_tag_family",
                }
    return {}


def _validate_method(sensor: dict, verification_type: str) -> str:
    method = (verification_type or "field_check").strip()
    allowed = METHODS_BY_SENSOR_TYPE.get(sensor.get("sensor_type"), {"field_check", "local_field_check"})
    if method not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"verification_type '{method}' is not valid for {sensor.get('tag')} ({sensor.get('sensor_type')}). Allowed: {sorted(allowed)}",
        )
    return method


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _datetime_from_ts(value: float) -> datetime:
    return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _timestamp(value: datetime | None) -> float | None:
    return value.replace(tzinfo=timezone.utc).timestamp() if value else None


def _loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
        return payload if isinstance(payload, list) else []
    except json.JSONDecodeError:
        return []
