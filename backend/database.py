"""
database.py — SQLAlchemy setup and models for ConfidenceOS V2.

V1 tables: SensorReading, AnomalyLog
V2 tables: ConfidenceLog, FlagEvent, ShiftHandoverLog

All tables now include plant_id for multi-plant support.
"""

import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text, Index
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./confidenceos.db")

# For SQLite, need check_same_thread=False for FastAPI async usage
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ── V1 Tables (extended with plant_id) ──────────────────────────────────────

class SensorReading(Base):
    """A single sensor reading at a point in time."""
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    sensor_id = Column(String(10), index=True, nullable=False)
    sensor_type = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    failure_mode = Column(String(50), nullable=True)


class AnomalyLog(Base):
    """Log of detected anomalies for the sensor health timeline."""
    __tablename__ = "anomaly_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    sensor_id = Column(String(10), index=True, nullable=False)
    anomaly_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


# ── V2 Tables ───────────────────────────────────────────────────────────────

class ConfidenceLog(Base):
    """
    Stores every confidence score per tick — enables predictions & forensics.
    Written by the WebSocket loop's read-through logging.
    """
    __tablename__ = "confidence_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    sensor_id = Column(String(10), index=True, nullable=False)
    confidence_pct = Column(Float, nullable=False)
    tier = Column(String(10), nullable=False)
    calibration_score = Column(Float, nullable=True)
    stability_score = Column(Float, nullable=True)
    cross_sensor_score = Column(Float, nullable=True)
    plausibility_score = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_confidence_log_plant_sensor_ts', 'plant_id', 'sensor_id', 'timestamp'),
    )


class FlagEvent(Base):
    """Logs mass-balance and confidence flag events with duration."""
    __tablename__ = "flag_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    sensor_id = Column(String(10), nullable=True)  # null for mass-balance flags
    flag_type = Column(String(50), nullable=False)  # mass_balance, confidence_low, etc.
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class ShiftHandoverLog(Base):
    """Persists generated shift handover briefs."""
    __tablename__ = "shift_handover_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    brief_text = Column(Text, nullable=False)
    source = Column(String(20), nullable=False)  # 'claude' or 'fallback'
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)


# ── Database lifecycle ──────────────────────────────────────────────────────

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


# ── Helper functions ────────────────────────────────────────────────────────

def log_anomaly(db, sensor_id, anomaly_type, description, severity, plant_id="plant-a"):
    """Persist an anomaly to the AnomalyLog table."""
    entry = AnomalyLog(
        plant_id=plant_id,
        sensor_id=sensor_id,
        anomaly_type=anomaly_type,
        description=description,
        severity=severity,
    )
    db.add(entry)
    db.commit()
    return entry


def get_recent_anomalies(db, sensor_id=None, limit=20, hours=24.0, plant_id=None):
    """Query recent anomalies from the AnomalyLog table."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    query = db.query(AnomalyLog).filter(AnomalyLog.timestamp >= cutoff)
    if sensor_id:
        query = query.filter(AnomalyLog.sensor_id == sensor_id)
    if plant_id:
        query = query.filter(AnomalyLog.plant_id == plant_id)
    entries = query.order_by(AnomalyLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "plant_id": e.plant_id,
            "sensor_id": e.sensor_id,
            "anomaly_type": e.anomaly_type,
            "description": e.description,
            "severity": e.severity,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in entries
    ]


def log_confidence(db, plant_id, sensor_id, confidence_pct, tier, sub_scores=None):
    """Log a confidence score to the ConfidenceLog table."""
    entry = ConfidenceLog(
        plant_id=plant_id,
        sensor_id=sensor_id,
        confidence_pct=confidence_pct,
        tier=tier,
        calibration_score=sub_scores.get("calibration") if sub_scores else None,
        stability_score=sub_scores.get("stability") if sub_scores else None,
        cross_sensor_score=sub_scores.get("cross_sensor") if sub_scores else None,
        plausibility_score=sub_scores.get("physical_plausibility") if sub_scores else None,
    )
    db.add(entry)
    return entry


def log_shift_handover(db, plant_id, brief_text, source):
    """Log a shift handover brief."""
    entry = ShiftHandoverLog(
        plant_id=plant_id,
        brief_text=brief_text,
        source=source,
    )
    db.add(entry)
    db.commit()
    return entry


def get_confidence_history(db, plant_id, sensor_id, hours=24.0):
    """Get confidence score history for a sensor — used by prediction engine."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    entries = (
        db.query(ConfidenceLog)
        .filter(
            ConfidenceLog.plant_id == plant_id,
            ConfidenceLog.sensor_id == sensor_id,
            ConfidenceLog.timestamp >= cutoff,
        )
        .order_by(ConfidenceLog.timestamp.asc())
        .all()
    )
    return [
        {
            "confidence_pct": e.confidence_pct,
            "tier": e.tier,
            "calibration_score": e.calibration_score,
            "stability_score": e.stability_score,
            "cross_sensor_score": e.cross_sensor_score,
            "plausibility_score": e.plausibility_score,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in entries
    ]


def get_sensor_readings_history(db, plant_id, sensor_id=None, hours=24.0, limit=None):
    """Get sensor reading history — used by forensics engine."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    query = (
        db.query(SensorReading)
        .filter(
            SensorReading.plant_id == plant_id,
            SensorReading.timestamp >= cutoff,
        )
    )
    if sensor_id:
        query = query.filter(SensorReading.sensor_id == sensor_id)
    query = query.order_by(SensorReading.timestamp.asc())
    if limit:
        query = query.limit(limit)
    return query.all()
