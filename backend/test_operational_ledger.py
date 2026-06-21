"""
test_operational_ledger.py - Tests for consolidated operational event trace.

Run from backend directory:
    python test_operational_ledger.py
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from operational_ledger import (
    get_operational_event,
    ledger_response,
    list_operational_events,
    record_operational_event,
    record_timeline_events,
)


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_operational_event_insert_list_and_dedupe():
    db = _session()
    first = record_operational_event(
        db,
        plant_id="plant-a",
        event_type="operator_note",
        source="shift_channel",
        source_id="note:1",
        subject_id="shift_channel",
        severity="INFO",
        message="Operator note pinned for handover.",
        event_id="plant-a:operator_note:note:1",
        commit=True,
    )
    second = record_operational_event(
        db,
        plant_id="plant-a",
        event_type="operator_note",
        source="shift_channel",
        source_id="note:1",
        subject_id="shift_channel",
        severity="INFO",
        message="Duplicate note should not create a second row.",
        event_id="plant-a:operator_note:note:1",
        commit=True,
    )
    events = list_operational_events(db, plant_id="plant-a")

    assert first["event_id"] == second["event_id"]
    assert len(events) == 1
    assert get_operational_event(db, "plant-a:operator_note:note:1")["source"] == "shift_channel"
    assert ledger_response("plant-a", events)["trace_summary"]["operator_notes"] == 1


def test_timeline_events_are_persisted_with_existing_ids():
    db = _session()
    record_timeline_events(
        db,
        [
            {
                "event_id": "plant-a:confidence_degraded:LT-5100",
                "plant_id": "plant-a",
                "event_type": "confidence_degraded",
                "severity": "WARNING",
                "message": "LT-5100 confidence degraded.",
                "timestamp": 1_700_000_000.0,
                "details": {"sensor_id": "LT-5100"},
            }
        ],
        commit=True,
    )
    events = list_operational_events(db, plant_id="plant-a")

    assert events[0]["event_id"] == "plant-a:confidence_degraded:LT-5100"
    assert events[0]["subject_id"] == "LT-5100"
    assert ledger_response("plant-a", events)["trace_summary"]["incident_events"] == 1


if __name__ == "__main__":
    test_operational_event_insert_list_and_dedupe()
    test_timeline_events_are_persisted_with_existing_ids()
    print("OK")
