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
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from asset_model import sensor_by_tag
from database import VerificationEvidence, VerificationTask, log_verification_event
from operational_ledger import record_verification_event

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
DEFAULT_EVIDENCE_REQUIRED = [
    {"id": "local_indication", "label": "Local indication", "type": "text", "required": True},
    {"id": "field_note", "label": "Field note", "type": "text", "required": True},
    {"id": "timestamped_confirmation", "label": "Time-stamped confirmation", "type": "text", "required": True},
]

# Procedure details: per-method procedure specifications for field technicians.
# Each entry provides the SOP reference, step-by-step field actions, expected
# evidence items, location hints, and clear closure criteria.
# These replace generic "local indication / field note" prompts with procedure-grade guidance.
PROCEDURE_DETAILS: dict[str, dict] = {
    "field_check": {
        "ref": "SOP-INST-001",
        "title": "General Instrument Field Check Procedure",
        "location_hint": "Locate instrument using tag ID on P&ID drawing. Check nameplate for equipment number and process connection point.",
        "expected_duration_min": 15,
        "steps": [
            "1. Confirm tag identity: match nameplate tag ID against task sensor ID.",
            "2. Observe local indicator/gauge and record value with engineering unit.",
            "3. Compare with DCS/HMI reading — calculate and record discrepancy.",
            "4. Inspect transmitter body for physical damage, corrosion, moisture, or loose connections.",
            "5. Check impulse lines / process connections for leaks or blockage signs.",
            "6. Record findings, sign, and timestamp. Note any follow-up actions required.",
        ],
        "evidence_items": [
            {"label": "Local reading value", "type": "numeric", "required": True},
            {"label": "Local reading unit", "type": "text", "required": True},
            {"label": "DCS reading at same time", "type": "numeric", "required": True},
            {"label": "Discrepancy (local − DCS)", "type": "numeric", "required": True},
            {"label": "Physical condition note", "type": "text", "required": True},
        ],
        "closure_criteria": "Local reading within ±5% of DCS reading, OR discrepancy explained and documented with corrective action plan.",
        "safety_note": "Do not isolate or interact with process connections unless a Permit to Work is in place.",
    },
    "local_field_check": {
        "ref": "SOP-INST-001",
        "title": "General Instrument Field Check Procedure",
        "location_hint": "Locate instrument using tag ID on P&ID drawing. Check nameplate for equipment number.",
        "expected_duration_min": 15,
        "steps": [
            "1. Confirm tag identity against nameplate.",
            "2. Record local indicator reading with unit.",
            "3. Compare with DCS reading; record discrepancy.",
            "4. Inspect for physical damage, leaks, or corrosion.",
            "5. Sign and timestamp findings.",
        ],
        "evidence_items": [
            {"label": "Local reading value", "type": "numeric", "required": True},
            {"label": "Local reading unit", "type": "text", "required": True},
            {"label": "Discrepancy from DCS", "type": "numeric", "required": True},
            {"label": "Physical condition note", "type": "text", "required": True},
        ],
        "closure_criteria": "Local reading within ±5% of DCS reading OR discrepancy explained.",
        "safety_note": "Do not interact with process connections without a Permit to Work.",
    },
    "manual_level_verification": {
        "ref": "SOP-INST-010",
        "title": "Level Transmitter Verification — Sight Glass / Independent Reference Method",
        "location_hint": "Locate the sight glass or independent level reference on the vessel. Confirm it is in service and its isolation valves are open.",
        "expected_duration_min": 20,
        "steps": [
            "1. Confirm sight glass is in service: check isolation valves are fully open, drain valve closed.",
            "2. Allow sight glass to stabilise (at least 60 seconds after opening).",
            "3. Read sight glass level from the graduated scale; record value with unit.",
            "4. Record DCS/HMI transmitter reading at the same time.",
            "5. Calculate discrepancy: sight glass level − DCS reading.",
            "6. If discrepancy > 5% of span, escalate to Engineer before accepting handover.",
            "7. Sign and timestamp all readings.",
        ],
        "evidence_items": [
            {"label": "Sight glass reading", "type": "numeric", "required": True},
            {"label": "Sight glass unit", "type": "text", "required": True},
            {"label": "DCS transmitter reading", "type": "numeric", "required": True},
            {"label": "Discrepancy (sight glass − DCS)", "type": "numeric", "required": True},
            {"label": "Sight glass condition", "type": "text", "required": True},
        ],
        "closure_criteria": "Sight glass reading within ±5% of DCS transmitter reading, or discrepancy documented with root cause and action plan.",
        "safety_note": "Do not open sight glass isolation valves if process is above relief pressure or under thermal stress.",
    },
    "sight_glass": {
        "ref": "SOP-INST-010",
        "title": "Level Transmitter Verification — Sight Glass Method",
        "location_hint": "Locate sight glass on vessel. Confirm isolation valves open and drain valve closed.",
        "expected_duration_min": 20,
        "steps": [
            "1. Verify sight glass is in service (isolation valves open).",
            "2. Stabilise 60 seconds, then read and record level with unit.",
            "3. Record DCS reading at same time.",
            "4. Calculate discrepancy.",
            "5. Sign and timestamp.",
        ],
        "evidence_items": [
            {"label": "Sight glass reading", "type": "numeric", "required": True},
            {"label": "DCS reading", "type": "numeric", "required": True},
            {"label": "Discrepancy", "type": "numeric", "required": True},
            {"label": "Sight glass condition", "type": "text", "required": True},
        ],
        "closure_criteria": "Discrepancy within ±5% of span OR explained with action plan.",
        "safety_note": "Obtain Permit to Work if sight glass connections require intervention.",
    },
    "manual_flow_verification": {
        "ref": "SOP-INST-020",
        "title": "Flow Meter Field Verification Procedure",
        "location_hint": "Locate flow element and transmitter housing. Check upstream/downstream isolation valve positions.",
        "expected_duration_min": 25,
        "steps": [
            "1. Check flow meter upstream and downstream condition (no isolation valves partially closed).",
            "2. Record DCS flow reading and engineering unit.",
            "3. Read any local flow indicator / totaliser if fitted; record value.",
            "4. Cross-check against adjacent flow meters or mass-balance expectation.",
            "5. Inspect impulse lines for leaks, freeze, or blockage.",
            "6. Document findings and any anomalies.",
        ],
        "evidence_items": [
            {"label": "DCS flow reading", "type": "numeric", "required": True},
            {"label": "Flow reading unit", "type": "text", "required": True},
            {"label": "Local indicator reading (if fitted)", "type": "numeric", "required": False},
            {"label": "Cross-check method used", "type": "text", "required": True},
            {"label": "Physical condition note", "type": "text", "required": True},
        ],
        "closure_criteria": "DCS reading consistent with cross-check within ±5%, OR discrepancy explained and action plan documented.",
        "safety_note": "Do not touch impulse lines without Permit to Work. Record upstream/downstream valve positions.",
    },
    "manual_pressure_verification": {
        "ref": "SOP-INST-030",
        "title": "Pressure Transmitter Loop Check Procedure",
        "location_hint": "Locate pressure transmitter and manifold valve. Identify the test point connection.",
        "expected_duration_min": 20,
        "steps": [
            "1. Identify transmitter manifold valve position (equalising valve closed for 3-valve manifold).",
            "2. If a local pressure gauge is fitted, read and record value.",
            "3. Record DCS pressure reading at same time.",
            "4. Calculate discrepancy: local gauge − DCS.",
            "5. Inspect transmitter body and impulse lines for leaks or damage.",
            "6. Document condition and any anomalies; sign and timestamp.",
        ],
        "evidence_items": [
            {"label": "Local gauge reading", "type": "numeric", "required": False},
            {"label": "DCS pressure reading", "type": "numeric", "required": True},
            {"label": "Pressure reading unit", "type": "text", "required": True},
            {"label": "Discrepancy (gauge − DCS)", "type": "numeric", "required": False},
            {"label": "Physical condition note", "type": "text", "required": True},
        ],
        "closure_criteria": "Local gauge reading within ±2% of DCS reading, OR no local gauge fitted and DCS reading is within expected process range.",
        "safety_note": "Do not open manifold valves without Permit to Work. High-pressure systems require two-person verification.",
    },
    "manual_temperature_verification": {
        "ref": "SOP-INST-040",
        "title": "Temperature Element Verification Procedure",
        "location_hint": "Locate thermowell and temperature transmitter housing. Note process fluid type and expected temperature range.",
        "expected_duration_min": 15,
        "steps": [
            "1. Record DCS temperature reading and engineering unit.",
            "2. Read any local temperature indicator (thermometer, local display) if fitted.",
            "3. Verify thermowell is correctly seated and connection head is closed.",
            "4. Inspect transmitter housing for moisture ingress or damage.",
            "5. Cross-check reading against adjacent temperature reference if available.",
            "6. Document findings, sign, and timestamp.",
        ],
        "evidence_items": [
            {"label": "DCS temperature reading", "type": "numeric", "required": True},
            {"label": "Temperature reading unit", "type": "text", "required": True},
            {"label": "Local indicator reading (if fitted)", "type": "numeric", "required": False},
            {"label": "Physical condition note", "type": "text", "required": True},
        ],
        "closure_criteria": "DCS reading consistent with process expectation and any local reference within ±3°C/°F, OR anomaly documented with action plan.",
        "safety_note": "High-temperature thermowells — do not remove from process without proper isolation and Permit to Work.",
    },
    "position_check": {
        "ref": "SOP-INST-050",
        "title": "Valve Position Indicator Check Procedure",
        "location_hint": "Locate valve and position transmitter/indicator. Confirm valve tag ID on actuator nameplate.",
        "expected_duration_min": 15,
        "steps": [
            "1. Confirm valve tag ID on actuator nameplate matches task sensor ID.",
            "2. Observe physical valve position (open/closed indicator, stem travel).",
            "3. Record DCS position indication (%) and physical observation.",
            "4. Check position transmitter (ZT) reading against actual valve travel.",
            "5. Inspect actuator for air supply, positioner feedback, and stem condition.",
            "6. Document findings, sign, and timestamp.",
        ],
        "evidence_items": [
            {"label": "DCS valve position (%)", "type": "numeric", "required": True},
            {"label": "Physical position observation", "type": "text", "required": True},
            {"label": "Actuator / positioner condition", "type": "text", "required": True},
        ],
        "closure_criteria": "Physical position consistent with DCS indication within ±5% open, OR discrepancy documented with action plan.",
        "safety_note": "Do not operate valve manually unless authorised and coordinated with control room. Obtain Permit to Work for any physical adjustment.",
    },
    "vibration_check": {
        "ref": "SOP-INST-060",
        "title": "Vibration Sensor Field Check Procedure",
        "location_hint": "Locate vibration sensor on rotating equipment. Check mounting base and cable connection.",
        "expected_duration_min": 20,
        "steps": [
            "1. Confirm sensor tag ID on housing matches task sensor ID.",
            "2. Check sensor mounting — confirm no loose bolts, cracks, or corrosion on base.",
            "3. Inspect cable connection for damage or loose fittings.",
            "4. Record DCS vibration reading and engineering unit.",
            "5. If handheld vibration meter available, take comparative reading and record value.",
            "6. Note any audible or tactile abnormality on the equipment.",
            "7. Document findings, sign, and timestamp.",
        ],
        "evidence_items": [
            {"label": "DCS vibration reading", "type": "numeric", "required": True},
            {"label": "Vibration unit (mm/s or in/s)", "type": "text", "required": True},
            {"label": "Handheld meter reading (if available)", "type": "numeric", "required": False},
            {"label": "Mounting and cable condition", "type": "text", "required": True},
            {"label": "Audible / tactile observation", "type": "text", "required": True},
        ],
        "closure_criteria": "Sensor reading consistent with handheld reference within ±10%, OR mounting integrity confirmed and reading anomaly explained.",
        "safety_note": "Do not touch rotating parts. Maintain safe distance. Use PPE appropriate to rotating equipment work.",
    },
}

# Backward-compatible simple reference string (used by existing callers that expect a string).
PROCEDURE_LINKS: dict[str, str] = {k: f"{v['ref']}: {v['title']}" for k, v in PROCEDURE_DETAILS.items()}


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
        evidence_required_json=json.dumps(_evidence_requirements_for_method(method)),
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
        record_verification_event(
            db,
            plant_id=plant_id,
            task_id=task.task_id,
            sensor_id=sensor_id,
            to_state="REQUESTED",
            from_state=None,
            actor=actor,
            actor_role=actor_role,
            evidence_note=note or ("Auto-generated verification requested." if source == "auto" else "Verification requested."),
            created_at=now,
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
    if state == "FIELD_CHECK_DONE":
        _validate_required_evidence(task, evidence_payload)
    if state == "ACCEPTED" and not _task_has_field_check_evidence(db, task):
        raise HTTPException(
            status_code=422,
            detail="Field-check evidence must be captured before acceptance.",
        )

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
        record_verification_event(
            db,
            plant_id=plant_id,
            task_id=task.task_id,
            sensor_id=task.sensor_id,
            to_state=state,
            from_state=current_state,
            actor=actor,
            actor_role=actor_role,
            evidence_note=note or None,
            created_at=now,
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
            record_verification_event(
                db,
                plant_id=plant_id,
                task_id=task.task_id,
                sensor_id=task.sensor_id,
                to_state="EXPIRED",
                from_state=from_state,
                actor="ConfidenceOS",
                actor_role="ConfidenceOS",
                evidence_note="Task expired before acceptance.",
                created_at=current,
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
    evidence_required = _normalize_evidence_items(_loads_list(task.evidence_required_json) or DEFAULT_EVIDENCE_REQUIRED)
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
        "evidence_required_labels": [item["label"] for item in evidence_required],
        "evidence_required_text": " / ".join(item["label"] for item in evidence_required),
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
        # Procedure link (ISA-S5.4 / site SOP reference — backward-compatible string)
        "procedure_ref": PROCEDURE_LINKS.get(task.verification_method, PROCEDURE_LINKS["field_check"]),
        # Full procedure detail: steps, evidence items, closure criteria, safety note
        "procedure_detail": PROCEDURE_DETAILS.get(task.verification_method, PROCEDURE_DETAILS["field_check"]),
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


def _evidence_requirements_for_method(method: str) -> list[dict]:
    detail = PROCEDURE_DETAILS.get(method) or PROCEDURE_DETAILS["field_check"]
    return _normalize_evidence_items(detail.get("evidence_items", []))


def _normalize_evidence_items(items: list[Any]) -> list[dict]:
    normalized = []
    for index, item in enumerate(items or []):
        if isinstance(item, str):
            label = item
            item_type = "text"
            required = True
            item_id = _evidence_item_id(label) or f"evidence_{index + 1}"
        elif isinstance(item, dict):
            label = str(item.get("label") or item.get("id") or f"Evidence item {index + 1}")
            item_type = str(item.get("type") or "text")
            required = bool(item.get("required", True))
            item_id = str(item.get("id") or _evidence_item_id(label) or f"evidence_{index + 1}")
        else:
            continue
        normalized.append({
            "id": item_id,
            "label": label,
            "type": item_type,
            "required": required,
        })
    return normalized


def _validate_required_evidence(task: VerificationTask, evidence: dict[str, Any]) -> None:
    required_items = [
        item for item in _normalize_evidence_items(_loads_list(task.evidence_required_json) or DEFAULT_EVIDENCE_REQUIRED)
        if item.get("required")
    ]
    provided = _provided_evidence_items(evidence)
    missing = []
    invalid_numeric = []
    for item in required_items:
        item_id = item["id"]
        value = provided.get(item_id)
        if value in (None, ""):
            missing.append(item_id)
            continue
        if item.get("type") == "numeric":
            try:
                float(value)
            except (TypeError, ValueError):
                invalid_numeric.append(item_id)
    if missing or invalid_numeric:
        detail = {
            "message": "Required structured field evidence is incomplete.",
            "missing_evidence_item_ids": missing,
            "invalid_numeric_evidence_item_ids": invalid_numeric,
            "required_evidence": required_items,
        }
        raise HTTPException(status_code=422, detail=detail)


def _provided_evidence_items(evidence: dict[str, Any]) -> dict[str, Any]:
    provided = {}
    for item in evidence.get("evidence_items") or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or _evidence_item_id(str(item.get("label") or "")))
        if item_id:
            provided[item_id] = item.get("value")
    return provided


def _task_has_field_check_evidence(db: Session, task: VerificationTask) -> bool:
    return (
        db.query(VerificationEvidence)
        .filter(
            VerificationEvidence.plant_id == task.plant_id,
            VerificationEvidence.task_id == task.task_id,
            VerificationEvidence.state == "FIELD_CHECK_DONE",
        )
        .first()
        is not None
    )


def _evidence_item_id(label: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "_", str(label or "").lower()).strip("_")
    return compact[:64]


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


def _loads_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        payload = json.loads(value)
        return payload if isinstance(payload, list) else []
    except json.JSONDecodeError:
        return []
