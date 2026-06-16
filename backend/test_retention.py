"""
test_retention.py — Tests for time-series retention/pruning (R5-A3).

ConfidenceLog and SensorReading are written every tick and would grow unbounded.
prune_timeseries() must delete rows older than keep_hours while preserving recent
rows and never touching the durable audit/workflow tables.

Run from backend directory:
    python test_retention.py
"""

import os
import sys
from datetime import datetime, timedelta

# Isolated SQLite file — must be set before importing database (engine built at import).
os.environ["DATABASE_URL"] = "sqlite:///./test_retention.db"

from database import (  # noqa: E402
    SessionLocal,
    init_db,
    ConfidenceLog,
    SensorReading,
    VerificationEvent,
    prune_timeseries,
)


def check(name: str, condition: bool, info: str = ""):
    if condition:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f": {info}" if info else ""))
        sys.exit(1)


def main():
    # Fresh DB
    if os.path.exists("./test_retention.db"):
        os.remove("./test_retention.db")
    init_db()
    db = SessionLocal()
    now = datetime.utcnow()
    old = now - timedelta(hours=100)
    recent = now - timedelta(hours=1)

    # Seed old + recent confidence/sensor rows, plus an audit event that must survive.
    db.add_all([
        ConfidenceLog(plant_id="plant-a", sensor_id="LT-5100", confidence_pct=50, tier="MEDIUM", timestamp=old),
        ConfidenceLog(plant_id="plant-a", sensor_id="LT-5100", confidence_pct=90, tier="HIGH", timestamp=recent),
        SensorReading(plant_id="plant-a", sensor_id="LT-5100", sensor_type="level", value=1.0, unit="ft", timestamp=old),
        SensorReading(plant_id="plant-a", sensor_id="LT-5100", sensor_type="level", value=2.0, unit="ft", timestamp=recent),
        VerificationEvent(plant_id="plant-a", task_id="t1", to_state="REQUESTED", created_at=old),
    ])
    db.commit()

    deleted = prune_timeseries(db, keep_hours=72)
    check("prune deletes old confidence row", deleted["confidence_log"] == 1, str(deleted))
    check("prune deletes old sensor row", deleted["sensor_readings"] == 1, str(deleted))

    check("recent confidence row kept", db.query(ConfidenceLog).count() == 1)
    check("recent sensor row kept", db.query(SensorReading).count() == 1)
    check("audit event untouched", db.query(VerificationEvent).count() == 1)

    # Idempotent: second sweep deletes nothing.
    again = prune_timeseries(db, keep_hours=72)
    check("second sweep is a no-op", again["confidence_log"] == 0 and again["sensor_readings"] == 0)

    db.close()
    print("\nAll retention tests passed.")


if __name__ == "__main__":
    main()
