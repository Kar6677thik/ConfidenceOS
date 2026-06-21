"""
operational_ledger.py - Consolidated operational event trace.

The ledger is prototype traceability, not a certified plant historian. It links
ConfidenceOS evidence across incidents, verification tasks, shift notes,
handover briefs, and compliance reports without writing process controls.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database import OperationalEvent


TRACE_TYPES = {
    "incident_events": {
        "mode_detected",
        "confidence_degraded",
        "mass_balance_divergence",
        "action_contract_created",
        "decision_freeze_created",
        "handover_debt_created",
    },
    "verification_events": {
        "verification_task_REQUESTED",
        "verification_task_ASSIGNED",
        "verification_task_FIELD_CHECK_DONE",
        "verification_task_ACCEPTED",
        "verification_task_REJECTED",
        "verification_task_EXPIRED",
    },
    "handover_events": {"handover_brief_generated"},
    "operator_notes": {"operator_note"},
    "compliance_events": {"compliance_report_generated"},
}


def event_ref(event: dict | OperationalEvent | None) -> dict | None:
    if not event:
        return None
    if isinstance(event, OperationalEvent):
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
            "subject_id": event.subject_id,
            "severity": event.severity,
            "message": event.message,
            "timestamp": _iso(event.created_at),
        }
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "source": event.get("source"),
        "subject_id": event.get("subject_id"),
        "severity": event.get("severity", "INFO"),
        "message": event.get("message"),
        "timestamp": event.get("timestamp") or event.get("created_at"),
    }


def event_to_dict(event: OperationalEvent) -> dict:
    payload = {}
    if event.payload_json:
        try:
            payload = json.loads(event.payload_json)
        except Exception:
            payload = {"parse_warning": "payload_json could not be decoded"}
    return {
        "event_id": event.event_id,
        "plant_id": event.plant_id,
        "event_type": event.event_type,
        "source": event.source,
        "source_id": event.source_id,
        "subject_id": event.subject_id,
        "severity": event.severity,
        "message": event.message,
        "timestamp": _iso(event.created_at),
        "payload": payload,
    }


def record_operational_event(
    db: Session,
    *,
    plant_id: str,
    event_type: str,
    source: str,
    source_id: str | None = None,
    subject_id: str | None = None,
    severity: str = "INFO",
    message: str = "",
    payload: dict | None = None,
    event_id: str | None = None,
    created_at: datetime | float | str | None = None,
    commit: bool = False,
) -> dict:
    _ensure_table(db)
    event_id = _event_id(event_id, plant_id, source, source_id, event_type, subject_id)
    existing = db.query(OperationalEvent).filter(OperationalEvent.event_id == event_id).one_or_none()
    if existing:
        return event_to_dict(existing)

    row = OperationalEvent(
        event_id=event_id,
        plant_id=plant_id,
        event_type=event_type,
        source=source,
        source_id=source_id,
        subject_id=subject_id,
        severity=(severity or "INFO").upper(),
        message=message or "",
        payload_json=json.dumps(payload or {}, default=str),
        created_at=_coerce_datetime(created_at),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return event_to_dict(row)


def record_many_operational_events(db: Session, events: list[dict], *, commit: bool = False) -> list[dict]:
    rows = []
    for event in events or []:
        rows.append(record_operational_event(db, commit=False, **event))
    if commit:
        db.commit()
    return rows


def record_timeline_events(db: Session, events: list[dict], *, commit: bool = False) -> list[dict]:
    payloads = []
    for event in events or []:
        details = event.get("details") or event.get("payload") or {}
        event_id = event.get("event_id")
        plant_id = event.get("plant_id") or _plant_from_event_id(event_id) or "plant-a"
        payloads.append({
            "event_id": event_id,
            "plant_id": plant_id,
            "event_type": event.get("event_type") or "incident_timeline",
            "source": "incident_timeline",
            "source_id": event_id,
            "subject_id": (
                details.get("sensor_id")
                or details.get("decision")
                or details.get("incident_id")
                or _subject_from_event_id(event_id)
            ),
            "severity": event.get("severity", "INFO"),
            "message": event.get("message", ""),
            "payload": details,
            "created_at": event.get("timestamp"),
        })
    return record_many_operational_events(db, payloads, commit=commit)


def record_verification_event(
    db: Session,
    *,
    plant_id: str,
    task_id: str,
    sensor_id: str | None,
    to_state: str,
    from_state: str | None = None,
    actor: str | None = None,
    actor_role: str | None = None,
    evidence_note: str | None = None,
    created_at: datetime | None = None,
    commit: bool = False,
) -> dict:
    state = (to_state or "UNKNOWN").upper()
    source_id = f"{task_id}:{from_state or 'created'}->{state}"
    if state in {"FIELD_CHECK_DONE", "ACCEPTED", "REJECTED", "EXPIRED"}:
        source_id = f"{source_id}:{int((created_at or datetime.now(timezone.utc)).timestamp())}"
    return record_operational_event(
        db,
        plant_id=plant_id,
        event_type=f"verification_task_{state}",
        source="verification_task",
        source_id=source_id,
        subject_id=sensor_id or task_id,
        severity="WARNING" if state in {"REQUESTED", "ASSIGNED", "EXPIRED", "REJECTED"} else "INFO",
        message=f"Verification task {task_id} moved to {state}.",
        payload={
            "task_id": task_id,
            "sensor_id": sensor_id,
            "from_state": from_state,
            "to_state": state,
            "actor": actor,
            "actor_role": actor_role,
            "evidence_note": evidence_note,
        },
        created_at=created_at,
        commit=commit,
    )


def list_operational_events(db: Session, *, plant_id: str, limit: int = 100, event_type: str | None = None) -> list[dict]:
    _ensure_table(db)
    query = db.query(OperationalEvent).filter(OperationalEvent.plant_id == plant_id)
    if event_type:
        query = query.filter(OperationalEvent.event_type == event_type)
    rows = query.order_by(OperationalEvent.created_at.desc(), OperationalEvent.id.desc()).limit(max(1, min(limit, 500))).all()
    return [event_to_dict(row) for row in rows]


def get_operational_event(db: Session, event_id: str) -> dict | None:
    _ensure_table(db)
    row = db.query(OperationalEvent).filter(OperationalEvent.event_id == event_id).one_or_none()
    return event_to_dict(row) if row else None


def ledger_response(plant_id: str, events: list[dict]) -> dict:
    return {
        "plant_id": plant_id,
        "events": events,
        "trace_summary": _trace_summary(events),
        "boundary": "Operational event IDs provide prototype traceability; this is not a certified plant historian.",
    }


def _trace_summary(events: list[dict]) -> dict:
    summary = {
        "incident_events": 0,
        "verification_events": 0,
        "handover_events": 0,
        "operator_notes": 0,
        "compliance_events": 0,
    }
    for event in events or []:
        event_type = event.get("event_type")
        source = event.get("source")
        if event_type in TRACE_TYPES["incident_events"] or source == "incident_timeline":
            summary["incident_events"] += 1
        if event_type in TRACE_TYPES["verification_events"] or source == "verification_task":
            summary["verification_events"] += 1
        if event_type in TRACE_TYPES["handover_events"] or source == "handover":
            summary["handover_events"] += 1
        if event_type in TRACE_TYPES["operator_notes"] or source == "shift_channel":
            summary["operator_notes"] += 1
        if event_type in TRACE_TYPES["compliance_events"] or source == "compliance_report":
            summary["compliance_events"] += 1
    return summary


def _ensure_table(db: Session) -> None:
    try:
        OperationalEvent.__table__.create(bind=db.get_bind(), checkfirst=True)
    except OperationalError:
        raise
    except Exception:
        # Some SQLAlchemy backends do not permit per-table DDL from this path.
        # The normal application startup still creates the table; let the caller
        # surface the original query error if creation was impossible.
        pass


def _event_id(explicit: str | None, plant_id: str, source: str, source_id: str | None, event_type: str, subject_id: str | None) -> str:
    if explicit:
        return _clean_id(explicit)[:140]
    parts = [plant_id, source, source_id or event_type, subject_id or ""]
    return _clean_id(":".join(str(part) for part in parts if part))[:140]


def _clean_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9:_./-]+", "-", str(value)).strip("-") or "event"


def _coerce_datetime(value: datetime | float | str | None) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value))
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except Exception:
            pass
    return datetime.utcnow()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _plant_from_event_id(event_id: str | None) -> str | None:
    if not event_id or ":" not in event_id:
        return None
    return event_id.split(":", 1)[0]


def _subject_from_event_id(event_id: str | None) -> str | None:
    if not event_id or ":" not in event_id:
        return None
    return event_id.rsplit(":", 1)[-1]
