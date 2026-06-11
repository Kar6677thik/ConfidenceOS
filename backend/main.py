"""
main.py — FastAPI application for ConfidenceOS backend.

Module 1 endpoints:
  - WebSocket /ws/sensors — streams sensor readings + confidence + mass-balance at 1 Hz
  - GET /api/sensors/history/{sensor_id} — returns last N readings from SQLite
  - GET /api/sensors/latest — returns most recent reading for each sensor
  - POST /api/scenario/load — load a failure scenario
  - POST /api/scenario/reset — reset simulator to clean state
  - GET /api/health — basic health check

Module 2 endpoints:
  - GET /api/confidence/{sensor_id} — current confidence score for a sensor
  - GET /api/confidence — current confidence scores for all sensors

Module 3 endpoints:
  - GET /api/mass-balance/flags — active mass-balance flags
  - GET /api/mass-balance/state — current mass-balance state

Module 4 endpoints (Sensor Health Timeline):
  - GET /api/sensors/{sensor_id}/health — calibration, anomalies, drift, maintenance
  - GET /api/anomalies — recent anomalies across all sensors
  - GET /api/anomalies/{sensor_id} — anomalies for a specific sensor

Module 5 endpoints (Startup Mode):
  - GET /api/mode — current operating mode
  - POST /api/mode/startup — toggle startup mode on/off
  - POST /api/mode/startup/acknowledge/{sensor_id} — acknowledge a stale reading

Module 6 endpoints (Shift Handover Brief):
  - POST /api/handover/generate — generate a new shift handover brief
  - GET /api/handover/latest — return the most recently generated brief
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    init_db, get_db,
    SensorReading as SensorReadingModel,
    AnomalyLog as AnomalyLogModel,
    log_anomaly, get_recent_anomalies,
)
from simulator import SensorSimulator
from confidence import ConfidenceEngine
from mass_balance import MassBalanceEngine, DEFAULT_TOLERANCE
from startup import StartupManager
from handover import HandoverBriefGenerator


# ─── Global instances ───────────────────────────────────────────────────────

simulator = SensorSimulator()
confidence_engine = ConfidenceEngine()
mass_balance_engine = MassBalanceEngine()
startup_manager = StartupManager()               # Module 5
handover_generator = HandoverBriefGenerator()     # Module 6

# Load default scenario if it exists
DEFAULT_SCENARIO = Path(__file__).parent / "scenario.json"
if DEFAULT_SCENARIO.exists():
    simulator.load_scenario(DEFAULT_SCENARIO)

# Set simulated calibration ages for demo
# LT-5100 is 47 days uncalibrated (Texas City scenario)
confidence_engine.set_calibration_age("LT-5100", 47.0)
confidence_engine.set_calibration_age("FI-2010", 12.0)
confidence_engine.set_calibration_age("FO-2020", 15.0)
confidence_engine.set_calibration_age("PT-3100", 5.0)
confidence_engine.set_calibration_age("TT-4100", 30.0)
confidence_engine.set_calibration_age("ZT-6100", 8.0)

# Store latest confidence results for REST access
_latest_confidence: dict[str, dict] = {}

# Store the latest mass-balance state for REST / handover access
_latest_mb_state: dict = {}

# Anomaly deduplication: (sensor_id:anomaly_type) → last-logged timestamp
# Prevents logging the same anomaly every second
_anomaly_cooldown: dict[str, float] = {}
ANOMALY_COOLDOWN_SECONDS = 60.0

# Base mass-balance tolerance (used to compute effective tolerance in startup mode)
BASE_MB_TOLERANCE = DEFAULT_TOLERANCE


# ─── Pydantic models for request bodies ─────────────────────────────────────

class StartupModeRequest(BaseModel):
    active: bool


# ─── App lifecycle ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    init_db()
    yield


app = FastAPI(
    title="ConfidenceOS API",
    description="Backend for ConfidenceOS — the HMI that knows what it does not know.",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── WebSocket: live sensor stream at 1 Hz ──────────────────────────────────

# Track active WebSocket connections
active_connections: list[WebSocket] = []


@app.websocket("/ws/sensors")
async def sensor_stream(websocket: WebSocket):
    """
    Stream all sensor readings at 1 Hz over WebSocket.
    Each message includes:
      - readings: raw sensor data
      - confidence: per-sensor confidence scores
      - mass_balance: implied level, measured level, discrepancy, flags
      - mode: current operating mode (NORMAL / STARTUP)
      - stale_flags: stale reading flags (startup mode only)
      - anomalies: newly detected anomalies this tick
    """
    global _latest_mb_state

    await websocket.accept()
    active_connections.append(websocket)

    # Get a DB session for persisting readings
    db = next(get_db())

    try:
        while True:
            now = time.time()

            # ── Apply startup mode overrides ────────────────────────────
            if startup_manager.is_active:
                confidence_engine.set_tier_thresholds(
                    startup_manager.tier_thresholds
                )
                mass_balance_engine.tolerance = (
                    BASE_MB_TOLERANCE * startup_manager.mass_balance_tolerance_multiplier
                )
            else:
                confidence_engine.clear_tier_thresholds()
                mass_balance_engine.tolerance = BASE_MB_TOLERANCE

            # ── Generate readings ───────────────────────────────────────
            readings = simulator.tick()

            # ── Compute confidence scores ───────────────────────────────
            confidence_results = confidence_engine.score_readings(readings)
            confidence_data = [r.to_dict() for r in confidence_results]

            # Update latest confidence cache
            for cr in confidence_results:
                _latest_confidence[cr.sensor_id] = cr.to_dict()

            # ── Update mass-balance engine ──────────────────────────────
            mb_state = mass_balance_engine.update(readings)
            _latest_mb_state = mb_state.to_dict()

            # ── Check stale readings (startup mode only) ────────────────
            stale_flags = startup_manager.check_stale_readings(readings, now)
            stale_data = [f.to_dict() for f in stale_flags]

            # ── Anomaly detection & logging (Module 4) ──────────────────
            new_anomalies = []

            for cr in confidence_results:
                if cr.tier in ("LOW", "CRITICAL"):
                    anomaly_type = f"confidence_{cr.tier.lower()}"
                    cooldown_key = f"{cr.sensor_id}:{anomaly_type}"
                    last_logged = _anomaly_cooldown.get(cooldown_key, 0)

                    if now - last_logged > ANOMALY_COOLDOWN_SECONDS:
                        description = "; ".join(cr.reasons) if cr.reasons else (
                            f"Confidence {cr.tier}: {cr.confidence_pct}%"
                        )
                        log_anomaly(
                            db, cr.sensor_id, anomaly_type,
                            description, cr.tier,
                        )
                        _anomaly_cooldown[cooldown_key] = now
                        new_anomalies.append({
                            "sensor_id": cr.sensor_id,
                            "anomaly_type": anomaly_type,
                            "description": description,
                            "severity": cr.tier,
                            "timestamp": now,
                        })

            # Log mass-balance flags as anomalies too
            for flag in mb_state.flags:
                cooldown_key = f"mass_balance:{flag.severity}"
                last_logged = _anomaly_cooldown.get(cooldown_key, 0)

                if now - last_logged > ANOMALY_COOLDOWN_SECONDS:
                    log_anomaly(
                        db, "SYSTEM", f"mass_balance_{flag.severity.lower()}",
                        flag.message, flag.severity,
                    )
                    _anomaly_cooldown[cooldown_key] = now
                    new_anomalies.append({
                        "sensor_id": "SYSTEM",
                        "anomaly_type": f"mass_balance_{flag.severity.lower()}",
                        "description": flag.message,
                        "severity": flag.severity,
                        "timestamp": now,
                    })

            # Log stale reading flags as anomalies
            for sf in stale_flags:
                cooldown_key = f"{sf.sensor_id}:stale_reading"
                last_logged = _anomaly_cooldown.get(cooldown_key, 0)

                if now - last_logged > ANOMALY_COOLDOWN_SECONDS:
                    desc = (
                        f"Stale reading: value {sf.last_value} unchanged for "
                        f"{sf.duration_seconds:.0f}s (startup mode threshold: "
                        f"{startup_manager.STALE_THRESHOLD_SECONDS:.0f}s)"
                    )
                    log_anomaly(
                        db, sf.sensor_id, "stale_reading",
                        desc, "WARNING",
                    )
                    _anomaly_cooldown[cooldown_key] = now
                    new_anomalies.append({
                        "sensor_id": sf.sensor_id,
                        "anomaly_type": "stale_reading",
                        "description": desc,
                        "severity": "WARNING",
                        "timestamp": now,
                    })

            # ── Persist sensor readings to SQLite ───────────────────────
            for r in readings:
                db_reading = SensorReadingModel(
                    sensor_id=r["sensor_id"],
                    sensor_type=r["sensor_type"],
                    value=r["value"],
                    unit=r["unit"],
                    timestamp=datetime.fromtimestamp(r["timestamp"]),
                    failure_mode=r["failure_mode"],
                )
                db.add(db_reading)
            db.commit()

            # ── Send to client ──────────────────────────────────────────
            await websocket.send_json({
                "type": "sensor_update",
                "timestamp": now,
                "readings": readings,
                "confidence": confidence_data,
                "mass_balance": _latest_mb_state,
                "mode": startup_manager.to_dict(),
                "stale_flags": stale_data,
                "new_anomalies": new_anomalies,
            })

            # Wait ~1 second (1 Hz)
            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        db.close()
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)
        db.close()


# ─── REST: sensor history ────────────────────────────────────────────────────

@app.get("/api/sensors/history/{sensor_id}")
def get_sensor_history(
    sensor_id: str,
    hours: float = Query(default=1.0, description="How many hours of history to return"),
    limit: int = Query(default=3600, description="Max number of readings to return"),
    db: Session = Depends(get_db),
):
    """Return historical readings for a sensor from SQLite."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    readings = (
        db.query(SensorReadingModel)
        .filter(
            SensorReadingModel.sensor_id == sensor_id,
            SensorReadingModel.timestamp >= cutoff,
        )
        .order_by(SensorReadingModel.timestamp.desc())
        .limit(limit)
        .all()
    )

    return {
        "sensor_id": sensor_id,
        "count": len(readings),
        "readings": [
            {
                "value": r.value,
                "unit": r.unit,
                "timestamp": r.timestamp.isoformat(),
                "failure_mode": r.failure_mode,
            }
            for r in reversed(readings)  # chronological order
        ],
    }


@app.get("/api/sensors/latest")
def get_latest_readings(db: Session = Depends(get_db)):
    """Return the most recent reading for each sensor."""
    from sqlalchemy import func

    # Subquery to get max timestamp per sensor
    subq = (
        db.query(
            SensorReadingModel.sensor_id,
            func.max(SensorReadingModel.timestamp).label("max_ts"),
        )
        .group_by(SensorReadingModel.sensor_id)
        .subquery()
    )

    readings = (
        db.query(SensorReadingModel)
        .join(
            subq,
            (SensorReadingModel.sensor_id == subq.c.sensor_id)
            & (SensorReadingModel.timestamp == subq.c.max_ts),
        )
        .all()
    )

    return {
        "readings": [
            {
                "sensor_id": r.sensor_id,
                "sensor_type": r.sensor_type,
                "value": r.value,
                "unit": r.unit,
                "timestamp": r.timestamp.isoformat(),
                "failure_mode": r.failure_mode,
            }
            for r in readings
        ]
    }


# ─── REST: confidence scores (Module 2) ─────────────────────────────────────

@app.get("/api/confidence/{sensor_id}")
def get_confidence(sensor_id: str):
    """Return the current confidence score for a specific sensor."""
    result = _latest_confidence.get(sensor_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No confidence data for sensor '{sensor_id}'. Is the WebSocket stream active?",
        )
    return result


@app.get("/api/confidence")
def get_all_confidence():
    """Return current confidence scores for all sensors."""
    if not _latest_confidence:
        return {"confidence": [], "message": "No data yet. Connect a WebSocket client to start streaming."}
    return {"confidence": list(_latest_confidence.values())}


# ─── REST: mass-balance flags (Module 3) ─────────────────────────────────────

@app.get("/api/mass-balance/flags")
def get_mass_balance_flags():
    """Return active mass-balance inconsistency flags."""
    return {
        "flags": [f.to_dict() for f in mass_balance_engine.active_flags],
        "count": len(mass_balance_engine.active_flags),
    }


@app.get("/api/mass-balance/state")
def get_mass_balance_state():
    """Return the current mass-balance state snapshot."""
    if mass_balance_engine._implied_level is None:
        return {"state": None, "message": "No data yet. Connect a WebSocket client to start streaming."}

    return {
        "state": {
            "implied_level": round(mass_balance_engine._implied_level, 2),
            "measured_level": mass_balance_engine._history[-1][3] if mass_balance_engine._history else None,
            "cumulative_flow_delta": round(mass_balance_engine._cumulative_flow_delta, 2),
            "window_seconds": mass_balance_engine.window_seconds,
            "tolerance": mass_balance_engine.tolerance,
            "history_entries": len(mass_balance_engine._history),
        }
    }


# ─── REST: Sensor Health Timeline (Module 4) ────────────────────────────────

@app.get("/api/sensors/{sensor_id}/health")
def get_sensor_health(
    sensor_id: str,
    db: Session = Depends(get_db),
):
    """
    Return comprehensive health data for a sensor.
    Includes calibration status, anomaly history, drift trend, and maintenance.
    """
    # Calibration data
    cal_age = confidence_engine.calibration_ages.get(sensor_id, 0.0)
    cal_interval = confidence_engine.calibration_interval_days
    cal_score = max(0.0, 1.0 - (cal_age / cal_interval)) if cal_age > 0 else 1.0

    if cal_age <= 0:
        cal_status = "current"
    elif cal_age / cal_interval >= 1.0:
        cal_status = "expired"
    elif cal_age / cal_interval >= 0.7:
        cal_status = "due_soon"
    else:
        cal_status = "current"

    # Anomaly history
    anomalies = get_recent_anomalies(db, sensor_id=sensor_id, limit=20, hours=24.0)

    # Drift trend from recent readings
    cutoff = datetime.utcnow() - timedelta(hours=1)
    recent_readings = (
        db.query(SensorReadingModel)
        .filter(
            SensorReadingModel.sensor_id == sensor_id,
            SensorReadingModel.timestamp >= cutoff,
        )
        .order_by(SensorReadingModel.timestamp.asc())
        .limit(120)
        .all()
    )

    drift_values = [r.value for r in recent_readings]
    drift_timestamps = [r.timestamp.isoformat() for r in recent_readings]

    if len(drift_values) > 1:
        mean_val = sum(drift_values) / len(drift_values)
        avg_deviation = sum(abs(v - mean_val) for v in drift_values) / len(drift_values)
    else:
        avg_deviation = 0.0

    # Simulated maintenance status
    work_orders = []
    if cal_status == "expired":
        work_orders.append({
            "type": "calibration",
            "priority": "critical",
            "description": f"Calibration expired — {cal_age:.0f} days since last calibration (interval: {cal_interval:.0f} days).",
        })
    elif cal_status == "due_soon":
        work_orders.append({
            "type": "calibration",
            "priority": "high",
            "description": f"Calibration due soon — {cal_age:.0f} days elapsed of {cal_interval:.0f}-day interval.",
        })

    if anomalies:
        critical_count = sum(1 for a in anomalies if a["severity"] == "CRITICAL")
        if critical_count > 0:
            work_orders.append({
                "type": "investigation",
                "priority": "high",
                "description": f"{critical_count} CRITICAL anomalies in last 24 hours — investigation required.",
            })

    maintenance_status = "attention_needed" if work_orders else "normal"

    return {
        "sensor_id": sensor_id,
        "calibration": {
            "age_days": cal_age,
            "interval_days": cal_interval,
            "score": round(cal_score, 3),
            "status": cal_status,
        },
        "anomalies": anomalies,
        "drift_trend": {
            "values": [round(v, 2) for v in drift_values],
            "timestamps": drift_timestamps,
            "average_deviation": round(avg_deviation, 3),
            "sample_count": len(drift_values),
        },
        "maintenance": {
            "status": maintenance_status,
            "work_orders": work_orders,
        },
    }


@app.get("/api/anomalies")
def get_all_anomalies(
    hours: float = Query(default=1.0, description="How many hours of history"),
    limit: int = Query(default=50, description="Max number of anomalies"),
    db: Session = Depends(get_db),
):
    """Return recent anomalies across all sensors."""
    anomalies = get_recent_anomalies(db, sensor_id=None, limit=limit, hours=hours)
    return {"anomalies": anomalies, "count": len(anomalies)}


@app.get("/api/anomalies/{sensor_id}")
def get_sensor_anomalies(
    sensor_id: str,
    hours: float = Query(default=24.0, description="How many hours of history"),
    limit: int = Query(default=20, description="Max number of anomalies"),
    db: Session = Depends(get_db),
):
    """Return recent anomalies for a specific sensor."""
    anomalies = get_recent_anomalies(db, sensor_id=sensor_id, limit=limit, hours=hours)
    return {"sensor_id": sensor_id, "anomalies": anomalies, "count": len(anomalies)}


# ─── REST: Startup Mode (Module 5) ──────────────────────────────────────────

@app.get("/api/mode")
def get_mode():
    """Return the current operating mode (NORMAL or STARTUP)."""
    return startup_manager.to_dict()


@app.post("/api/mode/startup")
def toggle_startup_mode(request: StartupModeRequest):
    """
    Toggle startup mode on or off.
    When active: confidence thresholds tighten, mass-balance tolerance halves,
    stale readings flagged after 8 minutes.
    """
    startup_manager.toggle(request.active)
    return {
        "status": "activated" if request.active else "deactivated",
        **startup_manager.to_dict(),
    }


@app.post("/api/mode/startup/acknowledge/{sensor_id}")
def acknowledge_stale_reading(sensor_id: str):
    """Acknowledge a stale reading flag (operator manual verification)."""
    success = startup_manager.acknowledge_stale(sensor_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No active stale reading flag for sensor '{sensor_id}'.",
        )
    return {
        "status": "acknowledged",
        "sensor_id": sensor_id,
    }


# ─── REST: Shift Handover Brief (Module 6) ──────────────────────────────────

@app.post("/api/handover/generate")
async def generate_handover_brief(db: Session = Depends(get_db)):
    """
    Generate a shift handover brief from current system state.
    Uses Claude API if ANTHROPIC_API_KEY is set, otherwise falls back
    to a structured template.
    """
    # Collect current system state
    confidence_data = list(_latest_confidence.values())

    if not confidence_data:
        raise HTTPException(
            status_code=400,
            detail="No sensor data available. Start the WebSocket stream first.",
        )

    anomalies = get_recent_anomalies(db, sensor_id=None, limit=20, hours=8.0)

    system_state = handover_generator.collect_system_state(
        confidence_data=confidence_data,
        mass_balance_state=_latest_mb_state,
        anomalies=anomalies,
        mode_state=startup_manager.to_dict(),
    )

    brief = await handover_generator.generate_brief(system_state)
    return brief


@app.get("/api/handover/latest")
def get_latest_handover():
    """Return the most recently generated handover brief."""
    brief = handover_generator.latest_brief
    if brief is None:
        return {
            "brief": None,
            "message": "No handover brief has been generated yet. "
                       "Use POST /api/handover/generate to create one.",
        }
    return brief


# ─── REST: scenario control ─────────────────────────────────────────────────

@app.post("/api/scenario/load")
def load_scenario(scenario_path: Optional[str] = None):
    """
    Load a failure injection scenario.
    If no path provided, loads the default scenario.json.
    """
    path = Path(scenario_path) if scenario_path else DEFAULT_SCENARIO
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {path}")

    simulator.load_scenario(path)
    simulator.reset()
    mass_balance_engine.reset()
    return {"status": "loaded", "scenario": str(path)}


@app.post("/api/scenario/reset")
def reset_scenario():
    """Reset the simulator clock and state. Failures will replay from the beginning."""
    simulator.reset()
    mass_balance_engine.reset()
    _anomaly_cooldown.clear()
    return {"status": "reset", "message": "Simulator and mass-balance reset. Failures will replay from t=0."}


@app.get("/api/health")
def health_check():
    """Basic health check."""
    return {
        "status": "ok",
        "uptime_seconds": round(simulator.elapsed(), 1),
        "tick_count": simulator.tick_count,
        "active_connections": len(active_connections),
        "mode": startup_manager.mode_name,
        "modules": {
            "sensor_simulator": "active",
            "confidence_engine": "active",
            "mass_balance_engine": "active",
            "startup_manager": "active",
            "handover_generator": "active",
        },
    }
