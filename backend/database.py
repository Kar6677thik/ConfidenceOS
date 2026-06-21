"""
database.py — SQLAlchemy setup and models for ConfidenceOS V2.

V1 tables: SensorReading, AnomalyLog
V2 tables: ConfidenceLog, FlagEvent, ShiftHandoverLog, AdaptiveEnvelopeLog

All tables now include plant_id for multi-plant support.
"""

import json
import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text, Index, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./confidenceos.db")

IS_SQLITE = "sqlite" in DATABASE_URL

# SQLite is fine for the demo, but it has a single-writer model. WAL + a busy
# timeout lets API requests and plant tick persistence share the same file
# without taking Runtime down during short writes.
connect_args = {"check_same_thread": False, "timeout": 30} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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


class AlarmState(Base):
    """
    ISA-18.2 alarm state machine per sensor per plant.

    States (ISA-18.2 §5):
      NORM          — no alarm condition, acknowledged
      UNACK_ALARM   — alarm active, operator not yet acknowledged
      ACK_ALARM     — alarm active, acknowledged
      UNACK_NORM    — alarm returned to normal, not yet acknowledged
      SHELVED       — alarm suppressed (time-limited)

    One row per (plant_id, sensor_id) pair; updated in place on each transition.
    """
    __tablename__ = "alarm_state"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False)
    sensor_id = Column(String(20), index=True, nullable=False)
    alarm_state = Column(String(20), nullable=False, default="NORM")
    alarm_class = Column(String(20), nullable=True)       # e.g. "process", "instrument"
    alarm_priority = Column(Integer, nullable=False, default=3)  # 1=critical…4=low (ISA-18.2)
    trigger_description = Column(Text, nullable=True)
    acknowledged_by = Column(String(80), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    shelved_until = Column(DateTime, nullable=True)
    shelved_by = Column(String(80), nullable=True)
    first_raised_at = Column(DateTime, nullable=True)
    last_raised_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    returned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_alarm_state_plant_sensor', 'plant_id', 'sensor_id', unique=True),
    )


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


class AdaptiveEnvelopeLog(Base):
    """Stores learned operating envelopes for adaptive plausibility checks."""
    __tablename__ = "adaptive_envelope_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    sensor_id = Column(String(10), index=True, nullable=False)
    sensor_type = Column(String(20), nullable=False)
    mean_value = Column(Float, nullable=False)
    std_dev = Column(Float, nullable=False)
    normal_min = Column(Float, nullable=False)
    normal_max = Column(Float, nullable=False)
    sample_count = Column(Integer, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)


class VerificationEvent(Base):
    """
    Immutable, append-only audit trail for field-verification task lifecycle.

    One row per state transition (and task creation). This is what makes the
    verification workflow a real, owned, auditable process rather than display
    state: every move records who did it, what role, when, and the evidence note.
    ConfidenceOS remains read-only to the process — this only logs the engineering
    verification workflow, never a control action.
    """
    __tablename__ = "verification_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    task_id = Column(String(80), index=True, nullable=False)
    sensor_id = Column(String(20), nullable=True)
    from_state = Column(String(20), nullable=True)   # null on creation
    to_state = Column(String(20), nullable=False)
    actor = Column(String(60), nullable=True)        # verified actor or compatibility label
    actor_role = Column(String(20), nullable=True)
    evidence_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_verification_events_plant_task_ts', 'plant_id', 'task_id', 'created_at'),
    )


# ── Database lifecycle ──────────────────────────────────────────────────────

class OperationalEvent(Base):
    """Append-only operational trace ledger for incident, verification, handover, and report events."""
    __tablename__ = "operational_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(String(140), index=True, nullable=False, unique=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    event_type = Column(String(60), index=True, nullable=False)
    source = Column(String(60), index=True, nullable=False)
    source_id = Column(String(140), index=True, nullable=True)
    subject_id = Column(String(80), index=True, nullable=True)
    severity = Column(String(20), nullable=False, default="INFO")
    message = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_operational_events_plant_ts', 'plant_id', 'created_at'),
        Index('ix_operational_events_plant_type_ts', 'plant_id', 'event_type', 'created_at'),
    )


class VerificationTask(Base):
    """Durable current state for field-verification tasks."""
    __tablename__ = "verification_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    task_id = Column(String(100), index=True, nullable=False, unique=True)
    token_id = Column(String(100), nullable=True)
    sensor_id = Column(String(20), index=True, nullable=False)
    state = Column(String(24), index=True, nullable=False, default="REQUESTED")
    source = Column(String(32), nullable=False, default="manual")
    assigned_role = Column(String(24), nullable=False, default="Maintenance")
    assigned_to = Column(String(80), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    field_checked_by = Column(String(80), nullable=True)
    field_checked_at = Column(DateTime, nullable=True)
    accepted_by = Column(String(80), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    rejected_by = Column(String(80), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    verification_method = Column(String(60), nullable=False, default="field_check")
    verification_type = Column(String(60), nullable=False, default="field_check")
    evidence_required_json = Column(Text, nullable=True)
    last_evidence_summary = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    valid_until = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)
    handover_required = Column(Integer, nullable=False, default=1)
    active = Column(Integer, nullable=False, default=1)
    closeout_status = Column(String(24), nullable=False, default="open")
    confidence_override = Column(Integer, nullable=False, default=0)
    usable_as_reference = Column(Integer, nullable=False, default=0)

    # CMMS / permit-to-work integration fields
    cmms_work_order = Column(String(64), nullable=True)       # e.g. "WO-2025-04871"
    permit_to_work_ref = Column(String(64), nullable=True)    # e.g. "PTW-0512"
    asset_tag_number = Column(String(64), nullable=True)      # ISA 5.1 asset tag
    loop_number = Column(String(32), nullable=True)           # e.g. "FIC-200"
    field_location = Column(String(128), nullable=True)       # e.g. "Unit 4 / Rack 7 / Bay 2"

    __table_args__ = (
        Index('ix_verification_tasks_plant_state', 'plant_id', 'state'),
    )


class VerificationEvidence(Base):
    """Structured evidence attached to verification-task transitions."""
    __tablename__ = "verification_evidence"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plant_id = Column(String(20), index=True, nullable=False, default="plant-a")
    task_id = Column(String(100), index=True, nullable=False)
    sensor_id = Column(String(20), index=True, nullable=False)
    state = Column(String(24), nullable=False)
    method = Column(String(80), nullable=True)
    field_reading_value = Column(Float, nullable=True)
    field_reading_unit = Column(String(24), nullable=True)
    technician_note = Column(Text, nullable=True)
    attachment_ref = Column(Text, nullable=True)
    captured_by = Column(String(80), nullable=True)
    accepted_by = Column(String(80), nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)
    evidence_json = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_verification_evidence_plant_task_ts', 'plant_id', 'task_id', 'captured_at'),
    )


class StudioImportBatch(Base):
    """Durable receipt for a raw-tag import batch used by the HMI Compiler."""
    __tablename__ = "studio_import_batches"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    import_batch_id = Column(String(80), index=True, nullable=False, unique=True)
    model_key = Column(String(80), index=True, nullable=False)
    source = Column(String(120), nullable=False, default="demo_import")
    raw_tags_json = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="IMPORTED")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_studio_import_batches_model_ts', 'model_key', 'created_at'),
    )


class HmiBuildArtifact(Base):
    """
    Immutable compiler build artifact receipt.

    The Runtime may still read the latest published manifest from lightweight
    Studio state for hackathon speed, but each build gets a durable SQLite copy
    with model key, validation result, manifest, diff, and receipts.
    """
    __tablename__ = "hmi_build_artifacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    build_id = Column(String(80), index=True, nullable=False, unique=True)
    model_key = Column(String(80), index=True, nullable=False)
    import_batch_id = Column(String(80), nullable=True)
    status = Column(String(32), nullable=False)
    can_publish = Column(Integer, nullable=False, default=0)
    state_revision = Column(Integer, nullable=True)
    validation_json = Column(Text, nullable=False)
    generated_manifest_json = Column(Text, nullable=True)
    publish_diff_json = Column(Text, nullable=True)
    receipts_json = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_hmi_build_artifacts_model_ts', 'model_key', 'created_at'),
    )


class User(Base):
    """
    Application user with role assignment and bcrypt-hashed password.

    Roles: Operator, Maintenance, Engineer, Manager, Auditor.
    Passwords are bcrypt-hashed; never stored in plaintext.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False)
    full_name = Column(String(128), nullable=True)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class StudioState(Base):
    """
    Persistent Studio compiler state, scoped per asset model.

    Replaces the file-backed studio_state.json so that model selection and
    build history survive restarts and are not shared as global process state.
    Each row represents one model's compiler workspace. Multiple models can
    coexist without clobbering each other.
    """
    __tablename__ = "studio_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_key = Column(String(64), nullable=False, unique=True, index=True)
    revision = Column(Integer, nullable=False, default=0)
    published_revision = Column(Integer, nullable=False, default=0)
    state_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create all tables and apply incremental column migrations. Safe to call multiple times."""
    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()


# ── Alarm state helpers (ISA-18.2) ───────────────────────────────────────────

def get_or_create_alarm(db, plant_id: str, sensor_id: str) -> "AlarmState":
    """Return the current alarm state row, creating NORM if not present."""
    row = db.query(AlarmState).filter(
        AlarmState.plant_id == plant_id,
        AlarmState.sensor_id == sensor_id,
    ).one_or_none()
    if row is None:
        row = AlarmState(plant_id=plant_id, sensor_id=sensor_id, alarm_state="NORM")
        db.add(row)
        db.flush()
    return row


def raise_alarm(db, plant_id: str, sensor_id: str, description: str,
                alarm_class: str = "instrument", priority: int = 3,
                commit: bool = True) -> "AlarmState":
    """Transition sensor alarm to UNACK_ALARM (or update if already raised)."""
    now = datetime.utcnow()
    row = get_or_create_alarm(db, plant_id, sensor_id)
    if row.alarm_state == "NORM":
        row.first_raised_at = now
    row.alarm_state = "UNACK_ALARM"
    row.alarm_class = alarm_class
    row.alarm_priority = priority
    row.trigger_description = description
    row.last_raised_at = now
    row.returned_at = None
    row.updated_at = now
    if commit:
        db.commit()
    return row


def acknowledge_alarm(db, plant_id: str, sensor_id: str,
                      actor: str, commit: bool = True) -> "AlarmState":
    """
    ISA-18.2 acknowledge transitions:
      UNACK_ALARM → ACK_ALARM
      UNACK_NORM  → NORM
    """
    now = datetime.utcnow()
    row = get_or_create_alarm(db, plant_id, sensor_id)
    if row.alarm_state == "UNACK_ALARM":
        row.alarm_state = "ACK_ALARM"
    elif row.alarm_state == "UNACK_NORM":
        row.alarm_state = "NORM"
    row.acknowledged_by = actor
    row.acknowledged_at = now
    row.updated_at = now
    if commit:
        db.commit()
    return row


def return_alarm_to_normal(db, plant_id: str, sensor_id: str,
                           commit: bool = True) -> "AlarmState":
    """
    ISA-18.2 return-to-normal transitions:
      UNACK_ALARM → UNACK_NORM
      ACK_ALARM   → NORM
    """
    now = datetime.utcnow()
    row = get_or_create_alarm(db, plant_id, sensor_id)
    if row.alarm_state == "UNACK_ALARM":
        row.alarm_state = "UNACK_NORM"
    elif row.alarm_state == "ACK_ALARM":
        row.alarm_state = "NORM"
    row.returned_at = now
    row.updated_at = now
    if commit:
        db.commit()
    return row


def shelve_alarm(db, plant_id: str, sensor_id: str, actor: str,
                 shelve_hours: float = 8.0, commit: bool = True) -> "AlarmState":
    """Shelve (suppress) an alarm for up to shelve_hours. ISA-18.2 §6.5."""
    now = datetime.utcnow()
    row = get_or_create_alarm(db, plant_id, sensor_id)
    row.alarm_state = "SHELVED"
    row.shelved_by = actor
    row.shelved_until = now + timedelta(hours=shelve_hours)
    row.updated_at = now
    if commit:
        db.commit()
    return row


def get_active_alarms(db, plant_id: str) -> list:
    """Return all non-NORM alarm rows for a plant, excluding expired shelves."""
    now = datetime.utcnow()
    rows = db.query(AlarmState).filter(
        AlarmState.plant_id == plant_id,
        AlarmState.alarm_state != "NORM",
    ).all()
    result = []
    for row in rows:
        if row.alarm_state == "SHELVED" and row.shelved_until and row.shelved_until <= now:
            row.alarm_state = "UNACK_ALARM"  # shelve expired — re-raise
            row.updated_at = now
        result.append(row)
    if any(r.alarm_state == "UNACK_ALARM" for r in result):
        db.commit()
    return result


def _migrate_add_columns():
    """Add new columns to existing tables using safe ALTER TABLE IF NOT EXISTS pattern."""
    migrations = [
        # CMMS / permit-to-work fields added to verification_tasks
        ("verification_tasks", "cmms_work_order",   "TEXT"),
        ("verification_tasks", "permit_to_work_ref", "TEXT"),
        ("verification_tasks", "asset_tag_number",   "TEXT"),
        ("verification_tasks", "loop_number",        "TEXT"),
        ("verification_tasks", "field_location",     "TEXT"),
        # User table fields (added with User model introduction)
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
            except Exception:
                # Column already exists — expected on subsequent startups
                conn.rollback()


def get_db():
    """FastAPI dependency — yields a DB session, closes on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Helper functions ────────────────────────────────────────────────────────

def log_anomaly(db, sensor_id, anomaly_type, description, severity, plant_id="plant-a", commit=True):
    """Persist an anomaly to the AnomalyLog table."""
    entry = AnomalyLog(
        plant_id=plant_id,
        sensor_id=sensor_id,
        anomaly_type=anomaly_type,
        description=description,
        severity=severity,
    )
    db.add(entry)
    if commit:
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


def log_verification_event(
    db,
    plant_id,
    task_id,
    to_state,
    from_state=None,
    sensor_id=None,
    actor=None,
    actor_role=None,
    evidence_note=None,
    commit=True,
):
    """Append an immutable verification-task lifecycle event to the audit trail."""
    entry = VerificationEvent(
        plant_id=plant_id,
        task_id=task_id,
        sensor_id=sensor_id,
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        actor_role=actor_role,
        evidence_note=evidence_note,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def get_verification_audit(db, plant_id, task_id=None, limit=200):
    """Return the immutable, time-ordered verification audit trail for a plant (optionally one task)."""
    query = db.query(VerificationEvent).filter(VerificationEvent.plant_id == plant_id)
    if task_id:
        query = query.filter(VerificationEvent.task_id == task_id)
    entries = query.order_by(VerificationEvent.created_at.asc(), VerificationEvent.id.asc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "plant_id": e.plant_id,
            "task_id": e.task_id,
            "sensor_id": e.sensor_id,
            "from_state": e.from_state,
            "to_state": e.to_state,
            "actor": e.actor,
            "actor_role": e.actor_role,
            "evidence_note": e.evidence_note,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


def record_import_batch(db, import_batch_id, model_key, raw_tags, source="demo_import", status="IMPORTED"):
    """Persist a raw-tag import batch receipt."""
    _ensure_schema()
    existing = db.query(StudioImportBatch).filter(StudioImportBatch.import_batch_id == import_batch_id).one_or_none()
    if existing:
        return existing
    entry = StudioImportBatch(
        import_batch_id=import_batch_id,
        model_key=model_key,
        source=source,
        raw_tags_json=json.dumps(raw_tags or []),
        status=status,
    )
    db.add(entry)
    db.commit()
    return entry


def record_hmi_build_artifact(db, build, model_key, import_batch_id=None, state_revision=None):
    """Persist one immutable HMI Compiler build artifact."""
    _ensure_schema()
    existing = db.query(HmiBuildArtifact).filter(HmiBuildArtifact.build_id == build.get("build_id")).one_or_none()
    if existing:
        return existing
    entry = HmiBuildArtifact(
        build_id=build.get("build_id"),
        model_key=model_key,
        import_batch_id=import_batch_id,
        status=build.get("status", "UNKNOWN"),
        can_publish=1 if build.get("can_publish") else 0,
        state_revision=state_revision,
        validation_json=json.dumps(build.get("validation", {})),
        generated_manifest_json=json.dumps(build.get("generated_manifest", {})),
        publish_diff_json=json.dumps(build.get("publish_diff", {})),
        receipts_json=json.dumps(build.get("receipts", [])),
    )
    db.add(entry)
    db.commit()
    return entry


def mark_hmi_build_published(db, build_id):
    """Mark a persisted build artifact as published without mutating its payload."""
    _ensure_schema()
    entry = db.query(HmiBuildArtifact).filter(HmiBuildArtifact.build_id == build_id).one_or_none()
    if not entry:
        return None
    if not entry.published_at:
        entry.published_at = datetime.utcnow()
        db.commit()
    return entry


def list_hmi_build_artifacts(db, model_key=None, limit=20):
    """Return recent immutable compiler build artifact receipts."""
    _ensure_schema()
    query = db.query(HmiBuildArtifact)
    if model_key:
        query = query.filter(HmiBuildArtifact.model_key == model_key)
    rows = query.order_by(HmiBuildArtifact.created_at.desc()).limit(limit).all()
    return [_hmi_build_artifact_to_dict(row) for row in rows]


def list_import_batches(db, model_key=None, limit=20):
    """Return recent imported tag batch receipts."""
    _ensure_schema()
    query = db.query(StudioImportBatch)
    if model_key:
        query = query.filter(StudioImportBatch.model_key == model_key)
    rows = query.order_by(StudioImportBatch.created_at.desc()).limit(limit).all()
    return [
        {
            "import_batch_id": row.import_batch_id,
            "model_key": row.model_key,
            "source": row.source,
            "raw_tags": _loads_json(row.raw_tags_json, []),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _hmi_build_artifact_to_dict(row):
    return {
        "build_id": row.build_id,
        "model_key": row.model_key,
        "import_batch_id": row.import_batch_id,
        "status": row.status,
        "can_publish": bool(row.can_publish),
        "state_revision": row.state_revision,
        "validation": _loads_json(row.validation_json, {}),
        "generated_manifest": _loads_json(row.generated_manifest_json, {}),
        "publish_diff": _loads_json(row.publish_diff_json, {}),
        "receipts": _loads_json(row.receipts_json, []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _loads_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _ensure_schema():
    Base.metadata.create_all(bind=engine)


def prune_timeseries(db, keep_hours=72.0):
    """
    Delete high-frequency time-series rows older than keep_hours.

    ConfidenceLog and SensorReading are written every tick and would otherwise
    grow unbounded (the single most concrete SQLite scaling bug). Workflow and
    audit tables (verification_events, hmi_build_artifacts, shift_handover_log)
    are intentionally NOT pruned — they are the durable record.

    Returns a dict of {table: rows_deleted}. Idempotent and safe to call often.
    """
    cutoff = datetime.utcnow() - timedelta(hours=keep_hours)
    deleted = {}
    try:
        deleted["confidence_log"] = (
            db.query(ConfidenceLog).filter(ConfidenceLog.timestamp < cutoff).delete(synchronize_session=False)
        )
        deleted["sensor_readings"] = (
            db.query(SensorReading).filter(SensorReading.timestamp < cutoff).delete(synchronize_session=False)
        )
        deleted["flag_events"] = (
            db.query(FlagEvent)
            .filter(FlagEvent.started_at < cutoff, FlagEvent.resolved_at.isnot(None))
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return deleted


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
