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
