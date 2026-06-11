"""
database.py — SQLAlchemy setup and models for ConfidenceOS.

Stores sensor reading history, calibration records, and anomaly logs.
Uses SQLite for zero-config hackathon deployment.
"""

import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./confidenceos.db")

# For SQLite, need check_same_thread=False for FastAPI async usage
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    """A single sensor reading at a point in time."""
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sensor_id = Column(String(10), index=True, nullable=False)  # e.g. "LT-5100"
    sensor_type = Column(String(20), nullable=False)  # e.g. "level", "flow_in"
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    # Failure injection metadata — what failure mode was active, if any
    failure_mode = Column(String(50), nullable=True)


class AnomalyLog(Base):
    """Log of detected anomalies for the sensor health timeline."""
    __tablename__ = "anomaly_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sensor_id = Column(String(10), index=True, nullable=False)
    anomaly_type = Column(String(50), nullable=False)  # drift, stuck, divergence, etc.
    description = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False)  # INFO, WARNING, CRITICAL
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


def init_db():
    """Create all tables. Safe to call multiple times."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session, closes on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Helper functions (Module 4: Sensor Health Timeline) ─────────────────────

def log_anomaly(
    db,
    sensor_id: str,
    anomaly_type: str,
    description: str,
    severity: str,
) -> AnomalyLog:
    """
    Persist an anomaly to the AnomalyLog table.

    Args:
        db: SQLAlchemy session
        sensor_id: e.g. "LT-5100"
        anomaly_type: e.g. "confidence_critical", "stuck_reading", "drift"
        description: human-readable reason string
        severity: "INFO", "WARNING", or "CRITICAL"

    Returns:
        The created AnomalyLog entry.
    """
    entry = AnomalyLog(
        sensor_id=sensor_id,
        anomaly_type=anomaly_type,
        description=description,
        severity=severity,
    )
    db.add(entry)
    db.commit()
    return entry


def get_recent_anomalies(
    db,
    sensor_id: str | None = None,
    limit: int = 20,
    hours: float = 24.0,
) -> list[dict]:
    """
    Query recent anomalies from the AnomalyLog table.

    Args:
        db: SQLAlchemy session
        sensor_id: filter to a specific sensor, or None for all
        limit: max number of results
        hours: how far back to look

    Returns:
        List of anomaly dicts sorted by timestamp descending.
    """
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = db.query(AnomalyLog).filter(AnomalyLog.timestamp >= cutoff)
    if sensor_id:
        query = query.filter(AnomalyLog.sensor_id == sensor_id)

    entries = (
        query.order_by(AnomalyLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": e.id,
            "sensor_id": e.sensor_id,
            "anomaly_type": e.anomaly_type,
            "description": e.description,
            "severity": e.severity,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in entries
    ]
