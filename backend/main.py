"""
main.py — FastAPI application for ConfidenceOS backend.

Module 1 endpoints:
  - WebSocket /ws/sensors — streams sensor readings + confidence + mass-balance at 1 Hz
  - GET /api/sensors/history/{sensor_id} — returns last N readings from SQLite
  - POST /api/scenario/load — load a failure scenario
  - POST /api/scenario/reset — reset simulator to clean state
  - GET /api/health — basic health check

Module 2 endpoints:
  - GET /api/confidence/{sensor_id} — current confidence score for a sensor
  - GET /api/confidence — current confidence scores for all sensors

Module 3 endpoints:
  - GET /api/mass-balance/flags — active mass-balance flags
  - GET /api/mass-balance/state — current mass-balance state
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
from sqlalchemy.orm import Session

from database import init_db, get_db, SensorReading as SensorReadingModel
from simulator import SensorSimulator
from confidence import ConfidenceEngine
from mass_balance import MassBalanceEngine


# ─── Global instances ───────────────────────────────────────────────────────

simulator = SensorSimulator()
confidence_engine = ConfidenceEngine()
mass_balance_engine = MassBalanceEngine()

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


# ─── App lifecycle ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    init_db()
    yield


app = FastAPI(
    title="ConfidenceOS API",
    description="Backend for ConfidenceOS — the HMI that knows what it does not know.",
    version="0.2.0",
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
    """
    await websocket.accept()
    active_connections.append(websocket)

    # Get a DB session for persisting readings
    db = next(get_db())

    try:
        while True:
            # Generate readings
            readings = simulator.tick()

            # Compute confidence scores
            confidence_results = confidence_engine.score_readings(readings)
            confidence_data = [r.to_dict() for r in confidence_results]

            # Update latest confidence cache
            for cr in confidence_results:
                _latest_confidence[cr.sensor_id] = cr.to_dict()

            # Update mass-balance engine
            mb_state = mass_balance_engine.update(readings)

            # Persist to SQLite
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

            # Send to client
            await websocket.send_json({
                "type": "sensor_update",
                "timestamp": time.time(),
                "readings": readings,
                "confidence": confidence_data,
                "mass_balance": mb_state.to_dict(),
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
    return {"status": "reset", "message": "Simulator and mass-balance reset. Failures will replay from t=0."}


@app.get("/api/health")
def health_check():
    """Basic health check."""
    return {
        "status": "ok",
        "uptime_seconds": round(simulator.elapsed(), 1),
        "tick_count": simulator.tick_count,
        "active_connections": len(active_connections),
        "modules": {
            "sensor_simulator": "active",
            "confidence_engine": "active",
            "mass_balance_engine": "active",
        },
    }
