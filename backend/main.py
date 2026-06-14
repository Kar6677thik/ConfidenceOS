"""
main.py — FastAPI application for ConfidenceOS V2.

V1 endpoints (maintained for backward compat):
  - WebSocket /ws/sensors — streams sensor readings + confidence + mass-balance at 1 Hz
  - GET /api/sensors/history/{sensor_id}, /api/sensors/latest
  - GET /api/confidence/{sensor_id}, /api/confidence
  - GET /api/mass-balance/flags, /api/mass-balance/state
  - GET /api/sensors/{sensor_id}/health
  - GET /api/anomalies, /api/anomalies/{sensor_id}
  - GET/POST /api/mode, /api/mode/startup
  - POST /api/handover/generate, GET /api/handover/latest
  - POST /api/scenario/load, /api/scenario/reset

V2 endpoints (new):
  - GET /api/fleet — fleet overview with risk scores for all plants
  - GET /api/predictions/{plant_id} — predictive failure forecasts
  - POST /api/query — natural language plant query
  - GET /api/graph/{plant_id} — causal graph state
  - GET /api/forensics/{plant_id} — historical data for replay
  - GET /api/forensics/presets — available preset incidents
  - POST /api/compliance/generate — compliance report data
"""

import asyncio
import base64
import json
import math
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
    ConfidenceLog as ConfidenceLogModel,
    log_anomaly, get_recent_anomalies,
    log_confidence, log_shift_handover,
    get_confidence_history,
)
from plants import PlantManager
from mass_balance import DEFAULT_TOLERANCE
from prediction import predict_all_sensors
from causal_graph import get_graph_state
from adaptive_thresholds import compute_adaptive_envelopes
from advisory import detect_plant_context, build_incidents, build_timeline_events
from assumptions import build_confidence_explanation, load_assumptions
from asset_model import load_asset_model
from decision_integrity import (
    active_verification_tokens,
    annotate_incidents_for_handover,
    build_handover_debt,
    build_score_sensitivity,
    build_trust_dependency_graph,
    update_confidence_debt,
)
from tag_provider import provider_catalog
import nlquery


# ─── Global instances ───────────────────────────────────────────────────────

plant_manager = PlantManager()

# Anomaly deduplication: (plant_id:sensor_id:anomaly_type) → last-logged timestamp
_anomaly_cooldown: dict[str, float] = {}
ANOMALY_COOLDOWN_SECONDS = 60.0

BASE_MB_TOLERANCE = DEFAULT_TOLERANCE

# Confidence logging throttle — log every N ticks to avoid DB bloat
_confidence_log_counter: dict[str, int] = {}
CONFIDENCE_LOG_INTERVAL = 5  # Log every 5 seconds
_plant_loop_status: dict[str, dict] = {}
INCIDENT_TIMELINE_MAX = 80


# ─── Pydantic models ────────────────────────────────────────────────────────

class StartupModeRequest(BaseModel):
    active: bool

class QueryRequest(BaseModel):
    question: str
    plant_id: str = "plant-a"

class ComplianceRequest(BaseModel):
    plant_id: str = "plant-a"
    hours: float = 24.0
    report_type: str = "full"  # full, alarm, sensor, handover

class SandboxRequest(BaseModel):
    plant_id: str = "plant-a"
    sensor_id: str
    failure_mode: str
    severity: str = "moderate"
    duration_hours: float = 6.0

class VerificationTokenRequest(BaseModel):
    sensor_id: str
    verification_type: str = "field_check"
    valid_minutes: float = 30.0
    note: str = ""


# ─── App lifecycle ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and start background plant ticking on startup."""
    init_db()
    # Start background tasks for all plants
    tasks = []
    for pid, plant in plant_manager.get_all().items():
        task = asyncio.create_task(_plant_tick_loop(pid, plant))
        tasks.append(task)
    yield
    # Cancel background tasks
    for task in tasks:
        task.cancel()


app = FastAPI(
    title="ConfidenceOS API",
    description="Backend for ConfidenceOS V2 — the HMI that knows what it does not know.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Background plant tick loop ─────────────────────────────────────────────

async def _plant_tick_loop(plant_id: str, plant):
    """Background loop that ticks each plant at 1 Hz and caches state."""
    db = next(get_db())
    tick_count = 0

    try:
        while True:
            now = time.time()

            # Apply startup mode overrides
            if plant.startup_manager.is_active:
                plant.confidence_engine.set_tier_thresholds(
                    plant.startup_manager.tier_thresholds
                )
                plant.mass_balance_engine.tolerance = (
                    BASE_MB_TOLERANCE * plant.startup_manager.mass_balance_tolerance_multiplier
                )
            else:
                plant.confidence_engine.clear_tier_thresholds()
                plant.mass_balance_engine.tolerance = BASE_MB_TOLERANCE

            # Read tags through the read-only provider abstraction. ConfidenceOS
            # observes plant state only; it does not write control commands.
            readings = plant.tag_provider.read_tags()
            plant.latest_readings = readings

            # Compute confidence scores
            confidence_results = plant.confidence_engine.score_readings(readings)
            confidence_data = [r.to_dict() for r in confidence_results]
            for item in confidence_data:
                item["handover_required"] = item.get("tier") in ("LOW", "CRITICAL")

            # Update cached confidence
            for cr in confidence_results:
                payload = cr.to_dict()
                payload["handover_required"] = payload.get("tier") in ("LOW", "CRITICAL")
                plant.latest_confidence[cr.sensor_id] = payload

            # Update mass-balance
            mb_state = plant.mass_balance_engine.update(readings)
            plant.latest_mb_state = mb_state.to_dict()

            # Check stale readings
            stale_flags = plant.startup_manager.check_stale_readings(readings, now)

            # Anomaly detection & logging
            new_anomalies = []
            for cr in confidence_results:
                if cr.tier in ("LOW", "CRITICAL"):
                    anomaly_type = f"confidence_{cr.tier.lower()}"
                    cooldown_key = f"{plant_id}:{cr.sensor_id}:{anomaly_type}"
                    last_logged = _anomaly_cooldown.get(cooldown_key, 0)
                    if now - last_logged > ANOMALY_COOLDOWN_SECONDS:
                        description = "; ".join(cr.reasons) if cr.reasons else f"Confidence {cr.tier}: {cr.confidence_pct}%"
                        log_anomaly(db, cr.sensor_id, anomaly_type, description, cr.tier, plant_id=plant_id)
                        _anomaly_cooldown[cooldown_key] = now
                        new_anomalies.append({
                            "sensor_id": cr.sensor_id,
                            "anomaly_type": anomaly_type,
                            "description": description,
                            "severity": cr.tier,
                            "timestamp": now,
                        })

            for flag in mb_state.flags:
                cooldown_key = f"{plant_id}:mass_balance:{flag.severity}"
                last_logged = _anomaly_cooldown.get(cooldown_key, 0)
                if now - last_logged > ANOMALY_COOLDOWN_SECONDS:
                    log_anomaly(db, "SYSTEM", f"mass_balance_{flag.severity.lower()}", flag.message, flag.severity, plant_id=plant_id)
                    _anomaly_cooldown[cooldown_key] = now
                    new_anomalies.append({
                        "sensor_id": "SYSTEM",
                        "anomaly_type": f"mass_balance_{flag.severity.lower()}",
                        "description": flag.message,
                        "severity": flag.severity,
                        "timestamp": now,
                    })

            for sf in stale_flags:
                cooldown_key = f"{plant_id}:{sf.sensor_id}:stale_reading"
                last_logged = _anomaly_cooldown.get(cooldown_key, 0)
                if now - last_logged > ANOMALY_COOLDOWN_SECONDS:
                    desc = f"Stale reading: value {sf.last_value} unchanged for {sf.duration_seconds:.0f}s"
                    log_anomaly(db, sf.sensor_id, "stale_reading", desc, "WARNING", plant_id=plant_id)
                    _anomaly_cooldown[cooldown_key] = now
                    new_anomalies.append({
                        "sensor_id": sf.sensor_id,
                        "anomaly_type": "stale_reading",
                        "description": desc,
                        "severity": "WARNING",
                        "timestamp": now,
                    })

            stale_payload = [sf.to_dict() for sf in stale_flags]
            mode_payload = plant.startup_manager.to_dict()
            inferred_mode = plant.mode_inference_engine.infer(
                readings=readings,
                confidence=confidence_data,
                mass_balance=plant.latest_mb_state,
                startup_mode=mode_payload,
                stale_flags=stale_payload,
            )
            mode_payload = {
                **mode_payload,
                "inferred_mode": inferred_mode.get("mode"),
                "inferred_state": inferred_mode.get("state"),
                "mode_inference": inferred_mode,
            }
            plant.latest_inferred_mode = inferred_mode
            plant.latest_mode_payload = mode_payload
            plant.latest_context = detect_plant_context(
                readings=readings,
                confidence=confidence_data,
                mass_balance=plant.latest_mb_state,
                mode=mode_payload,
                stale_flags=stale_payload,
                inferred_mode=inferred_mode,
            )
            plant.latest_incidents = build_incidents(
                plant_id=plant_id,
                readings=readings,
                confidence=confidence_data,
                mass_balance=plant.latest_mb_state,
                stale_flags=stale_payload,
                plant_context=plant.latest_context,
            )
            plant.latest_incidents = annotate_incidents_for_handover(plant.latest_incidents)
            plant.latest_confidence_debt = update_confidence_debt(
                plant.confidence_debt_state,
                confidence_data,
                readings,
                plant.latest_context,
                now,
            )
            plant.latest_handover_debt = build_handover_debt(
                plant_id=plant_id,
                incidents=plant.latest_incidents,
                confidence=confidence_data,
                verification_tokens=plant.verification_tokens,
                confidence_debt=plant.latest_confidence_debt,
                now=now,
            )
            tick_events = build_timeline_events(
                plant_id=plant_id,
                inferred_mode=inferred_mode,
                confidence=confidence_data,
                mass_balance=plant.latest_mb_state,
                incidents=plant.latest_incidents,
                timestamp=now,
            )
            tick_events.extend(_handover_debt_events(plant_id, plant.latest_handover_debt, now))
            plant.latest_incident_timeline = _merge_incident_timeline(
                plant.latest_incident_timeline,
                tick_events,
            )
            plant.latest_new_anomalies = new_anomalies

            # Persist sensor readings
            for r in readings:
                db_reading = SensorReadingModel(
                    plant_id=plant_id,
                    sensor_id=r["sensor_id"],
                    sensor_type=r["sensor_type"],
                    value=r["value"],
                    unit=r["unit"],
                    timestamp=datetime.fromtimestamp(r["timestamp"]),
                    failure_mode=r["failure_mode"],
                )
                db.add(db_reading)

            # V2: Log confidence scores (throttled)
            tick_count += 1
            if tick_count % CONFIDENCE_LOG_INTERVAL == 0:
                for cr in confidence_results:
                    log_confidence(
                        db, plant_id, cr.sensor_id,
                        cr.confidence_pct, cr.tier,
                        sub_scores={
                            "calibration": cr.sub_scores.calibration_score,
                            "stability": cr.sub_scores.stability_score,
                            "cross_sensor": cr.sub_scores.cross_sensor_score,
                            "physical_plausibility": cr.sub_scores.physical_plausibility_score,
                        }
                    )

            db.commit()
            _plant_loop_status[plant_id] = {
                "status": "ok",
                "last_tick": now,
                "tick_count": plant.tag_provider.tick_count,
                "last_error": None,
            }
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        db.close()
    except Exception as e:
        print(f"[PlantTick] Error in {plant_id}: {e}")
        _plant_loop_status[plant_id] = {
            "status": "error",
            "last_tick": time.time(),
            "tick_count": getattr(plant.tag_provider, "tick_count", 0),
            "last_error": str(e),
        }
        db.close()


# ─── WebSocket: live sensor stream at 1 Hz ──────────────────────────────────

active_connections: list[WebSocket] = []


def _latest_reading_for_sensor(readings: list[dict], sensor_id: str) -> dict | None:
    for reading in readings or []:
        if reading.get("sensor_id") == sensor_id:
            return reading
    return None


def _merge_incident_timeline(existing: list[dict], current_events: list[dict]) -> list[dict]:
    """Append only new active event keys, keeping a compact rolling history."""
    seen = {event.get("event_id") for event in existing}
    merged = list(existing)
    for event in current_events:
        if event.get("event_id") in seen:
            continue
        merged.append(event)
        seen.add(event.get("event_id"))
    return merged[-INCIDENT_TIMELINE_MAX:]


def _handover_debt_events(plant_id: str, debt: dict, timestamp: float) -> list[dict]:
    """Create stable timeline events for handover debt entries."""
    events = []
    for entry in (debt or {}).get("entries", []):
        events.append({
            "event_id": f"{plant_id}:handover_debt:{entry.get('id')}",
            "plant_id": plant_id,
            "event_type": "handover_debt_created",
            "subject": entry.get("id"),
            "severity": entry.get("severity", "WARNING"),
            "message": entry.get("title", "Handover debt created."),
            "timestamp": timestamp,
            "details": {
                "type": entry.get("type"),
                "required_action": entry.get("required_action"),
                "handover_required": True,
            },
        })
    return events


@app.websocket("/ws/sensors")
async def sensor_stream(
    websocket: WebSocket,
    plant_id: str = Query(default="plant-a"),
):
    """
    Stream sensor readings at 1 Hz over WebSocket for a specific plant.
    Reads from the cached state updated by the background tick loop.
    """
    await websocket.accept()
    active_connections.append(websocket)
    plant = plant_manager.get(plant_id)

    try:
        while True:
            now = time.time()
            readings = plant.latest_readings
            confidence_data = list(plant.latest_confidence.values())
            stale_flags = plant.startup_manager.check_stale_readings(readings, now) if readings else []

            await websocket.send_json({
                "type": "sensor_update",
                "plant_id": plant_id,
                "timestamp": now,
                "readings": readings,
                "confidence": confidence_data,
                "mass_balance": plant.latest_mb_state,
                "mode": {
                    **plant.startup_manager.to_dict(),
                    "inferred_mode": plant.latest_inferred_mode.get("mode"),
                    "inferred_state": plant.latest_inferred_mode.get("state"),
                    "mode_inference": plant.latest_inferred_mode,
                },
                "stale_flags": [f.to_dict() for f in stale_flags],
                "new_anomalies": plant.latest_new_anomalies,
                "plant_context": plant.latest_context,
                "incidents": plant.latest_incidents,
                "incident_timeline": plant.latest_incident_timeline,
                "verification_tokens": active_verification_tokens(plant.verification_tokens, now),
                "handover_debt": plant.latest_handover_debt,
                "confidence_debt": plant.latest_confidence_debt,
            })

            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)


# ─── REST: sensor history ────────────────────────────────────────────────────

@app.get("/api/sensors/history/{sensor_id}")
def get_sensor_history(
    sensor_id: str,
    plant_id: str = Query(default="plant-a"),
    hours: float = Query(default=1.0),
    limit: int = Query(default=3600),
    db: Session = Depends(get_db),
):
    """Return historical readings for a sensor from SQLite."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    readings = (
        db.query(SensorReadingModel)
        .filter(
            SensorReadingModel.plant_id == plant_id,
            SensorReadingModel.sensor_id == sensor_id,
            SensorReadingModel.timestamp >= cutoff,
        )
        .order_by(SensorReadingModel.timestamp.desc())
        .limit(limit)
        .all()
    )
    return {
        "sensor_id": sensor_id,
        "plant_id": plant_id,
        "count": len(readings),
        "readings": [
            {"value": r.value, "unit": r.unit, "timestamp": r.timestamp.isoformat(), "failure_mode": r.failure_mode}
            for r in reversed(readings)
        ],
    }


@app.get("/api/sensors/latest")
def get_latest_readings(plant_id: str = Query(default="plant-a")):
    """Return the most recent reading for each sensor (from cache)."""
    plant = plant_manager.get(plant_id)
    if not plant.latest_readings:
        return {"readings": [], "message": "No data yet."}
    return {"readings": plant.latest_readings}


# ─── REST: confidence scores (Module 2) ─────────────────────────────────────

@app.get("/api/confidence/{sensor_id}")
def get_confidence(sensor_id: str, plant_id: str = Query(default="plant-a")):
    """Return the current confidence score for a specific sensor."""
    plant = plant_manager.get(plant_id)
    result = plant.latest_confidence.get(sensor_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No confidence data for sensor '{sensor_id}'.")
    return result


@app.get("/api/confidence")
def get_all_confidence(plant_id: str = Query(default="plant-a")):
    """Return current confidence scores for all sensors."""
    plant = plant_manager.get(plant_id)
    if not plant.latest_confidence:
        return {"confidence": [], "message": "No data yet."}
    return {"confidence": list(plant.latest_confidence.values())}


@app.get("/api/confidence/explain/{sensor_id}")
def explain_confidence(sensor_id: str, plant_id: str = Query(default="plant-a")):
    """Return deterministic confidence explanation for a specific sensor."""
    plant = plant_manager.get(plant_id)
    result = plant.latest_confidence.get(sensor_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No confidence data for sensor '{sensor_id}'.")

    reading = _latest_reading_for_sensor(plant.latest_readings, sensor_id)
    assumptions = load_assumptions()
    return build_confidence_explanation(sensor_id, result, reading, assumptions)


@app.get("/api/confidence/{sensor_id}/explain")
def explain_confidence_alias(sensor_id: str, plant_id: str = Query(default="plant-a")):
    """Alias for clients that prefer sensor-scoped explain URLs."""
    return explain_confidence(sensor_id=sensor_id, plant_id=plant_id)


@app.get("/api/confidence/sensitivity/{sensor_id}")
def get_score_sensitivity(
    sensor_id: str,
    plant_id: str = Query(default="plant-a"),
    role: str = Query(default="Engineer"),
):
    """Engineer-only deterministic score sensitivity view data."""
    if role != "Engineer":
        raise HTTPException(status_code=403, detail="Score sensitivity requires Engineer role.")
    plant = plant_manager.get(plant_id)
    result = plant.latest_confidence.get(sensor_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No confidence data for sensor '{sensor_id}'.")
    return build_score_sensitivity(sensor_id, result, role=role)


@app.get("/api/confidence/debt/{plant_id}")
def get_confidence_debt(plant_id: str):
    """Return confidence debt for maintenance prioritization, not failure prediction."""
    plant = plant_manager.get(plant_id)
    return {
        "plant_id": plant_id,
        "metric": "confidence_debt",
        "definition": "time below HIGH confidence tier x criticality x active context weight",
        "not_predictive_failure": True,
        "items": plant.latest_confidence_debt,
        "count": len(plant.latest_confidence_debt),
        "timestamp": time.time(),
    }


@app.get("/api/assumptions")
def get_assumptions():
    """Return the governed engineering assumption register."""
    assumptions = load_assumptions()
    return {
        "assumptions": assumptions,
        "count": len(assumptions),
        "source": "backend/assumptions.json",
    }


@app.get("/api/asset-model")
def get_asset_model():
    """Return the demo vessel asset model used for trust/evidence metadata."""
    return {
        "asset_model": load_asset_model(),
        "source": "backend/asset_model.json",
        "read_only_trust_layer": True,
    }


@app.get("/api/integration/read-only-layer")
def get_read_only_integration_layer():
    """Describe how ConfidenceOS sits beside control systems as a read-only trust layer."""
    asset_model = load_asset_model()
    return {
        "read_only": True,
        "control_writes_enabled": False,
        "writes_supported": False,
        "positioning": (
            "ConfidenceOS subscribes to tag data and publishes trust, evidence, "
            "handover, and decision-freeze metadata. It does not replace DCS/PLC/HMI "
            "control layers or write commands to ABB-class systems."
        ),
        "active_providers": {
            plant_id: plant.tag_provider.to_dict()
            for plant_id, plant in plant_manager.get_all().items()
        },
        "available_providers": provider_catalog(),
        "asset_model_id": asset_model.get("model_id"),
        "equipment_id": asset_model.get("equipment", {}).get("equipment_id"),
    }


# ─── REST: mass-balance flags (Module 3) ─────────────────────────────────────

@app.get("/api/mass-balance/flags")
def get_mass_balance_flags(plant_id: str = Query(default="plant-a")):
    """Return active mass-balance inconsistency flags."""
    plant = plant_manager.get(plant_id)
    return {
        "flags": [f.to_dict() for f in plant.mass_balance_engine.active_flags],
        "count": len(plant.mass_balance_engine.active_flags),
    }


@app.get("/api/mass-balance/state")
def get_mass_balance_state(plant_id: str = Query(default="plant-a")):
    """Return the current mass-balance state snapshot."""
    plant = plant_manager.get(plant_id)
    if plant.mass_balance_engine._implied_level is None:
        return {"state": None, "message": "No data yet."}
    return {
        "state": {
            "implied_level": round(plant.mass_balance_engine._implied_level, 2),
            "measured_level": plant.mass_balance_engine._history[-1][3] if plant.mass_balance_engine._history else None,
            "cumulative_flow_delta": round(plant.mass_balance_engine._cumulative_flow_delta, 2),
            "window_seconds": plant.mass_balance_engine.window_seconds,
            "tolerance": plant.mass_balance_engine.tolerance,
            "history_entries": len(plant.mass_balance_engine._history),
        }
    }


# ─── REST: Sensor Health Timeline (Module 4) ────────────────────────────────

@app.get("/api/sensors/{sensor_id}/health")
def get_sensor_health(sensor_id: str, plant_id: str = Query(default="plant-a"), db: Session = Depends(get_db)):
    """Return comprehensive health data for a sensor."""
    plant = plant_manager.get(plant_id)
    ce = plant.confidence_engine

    cal_age = ce.calibration_ages.get(sensor_id, 0.0)
    cal_interval = ce.calibration_interval_days
    cal_score = max(0.0, 1.0 - (cal_age / cal_interval)) if cal_age > 0 else 1.0

    if cal_age <= 0:
        cal_status = "current"
    elif cal_age / cal_interval >= 1.0:
        cal_status = "expired"
    elif cal_age / cal_interval >= 0.7:
        cal_status = "due_soon"
    else:
        cal_status = "current"

    anomalies = get_recent_anomalies(db, sensor_id=sensor_id, limit=20, hours=24.0, plant_id=plant_id)

    cutoff = datetime.utcnow() - timedelta(hours=1)
    recent_readings = (
        db.query(SensorReadingModel)
        .filter(
            SensorReadingModel.plant_id == plant_id,
            SensorReadingModel.sensor_id == sensor_id,
            SensorReadingModel.timestamp >= cutoff,
        )
        .order_by(SensorReadingModel.timestamp.asc())
        .limit(120)
        .all()
    )

    drift_values = [r.value for r in recent_readings]
    drift_timestamps = [r.timestamp.isoformat() for r in recent_readings]
    avg_deviation = sum(abs(v - sum(drift_values)/len(drift_values)) for v in drift_values) / len(drift_values) if len(drift_values) > 1 else 0.0

    work_orders = []
    if cal_status == "expired":
        work_orders.append({"type": "calibration", "priority": "critical", "description": f"Calibration expired — {cal_age:.0f} days."})
    elif cal_status == "due_soon":
        work_orders.append({"type": "calibration", "priority": "high", "description": f"Calibration due soon — {cal_age:.0f} days elapsed."})

    return {
        "sensor_id": sensor_id,
        "plant_id": plant_id,
        "calibration": {"age_days": cal_age, "interval_days": cal_interval, "score": round(cal_score, 3), "status": cal_status},
        "anomalies": anomalies,
        "drift_trend": {"values": [round(v, 2) for v in drift_values], "timestamps": drift_timestamps, "average_deviation": round(avg_deviation, 3), "sample_count": len(drift_values)},
        "maintenance": {"status": "attention_needed" if work_orders else "normal", "work_orders": work_orders},
    }


@app.get("/api/anomalies")
def get_all_anomalies(
    plant_id: str = Query(default="plant-a"),
    hours: float = Query(default=1.0),
    limit: int = Query(default=50),
    db: Session = Depends(get_db),
):
    """Return recent anomalies across all sensors."""
    anomalies = get_recent_anomalies(db, sensor_id=None, limit=limit, hours=hours, plant_id=plant_id)
    return {"anomalies": anomalies, "count": len(anomalies)}


@app.get("/api/anomalies/{sensor_id}")
def get_sensor_anomalies(
    sensor_id: str,
    plant_id: str = Query(default="plant-a"),
    hours: float = Query(default=24.0),
    limit: int = Query(default=20),
    db: Session = Depends(get_db),
):
    """Return recent anomalies for a specific sensor."""
    anomalies = get_recent_anomalies(db, sensor_id=sensor_id, limit=limit, hours=hours, plant_id=plant_id)
    return {"sensor_id": sensor_id, "anomalies": anomalies, "count": len(anomalies)}


# ─── REST: Startup Mode (Module 5) ──────────────────────────────────────────

@app.get("/api/mode")
def get_mode(plant_id: str = Query(default="plant-a")):
    """Return the current operating mode."""
    plant = plant_manager.get(plant_id)
    return {
        **plant.startup_manager.to_dict(),
        "inferred_mode": plant.latest_inferred_mode.get("mode"),
        "inferred_state": plant.latest_inferred_mode.get("state"),
        "mode_inference": plant.latest_inferred_mode,
    }


@app.post("/api/mode/startup")
def toggle_startup_mode(request: StartupModeRequest, plant_id: str = Query(default="plant-a")):
    """Toggle startup mode on or off."""
    plant = plant_manager.get(plant_id)
    plant.startup_manager.toggle(request.active)
    return {
        "status": "activated" if request.active else "deactivated",
        **plant.startup_manager.to_dict(),
        "inferred_mode": plant.latest_inferred_mode.get("mode"),
        "inferred_state": plant.latest_inferred_mode.get("state"),
        "mode_inference": plant.latest_inferred_mode,
    }


@app.post("/api/mode/startup/acknowledge/{sensor_id}")
def acknowledge_stale_reading(sensor_id: str, plant_id: str = Query(default="plant-a")):
    """Acknowledge a stale reading flag."""
    plant = plant_manager.get(plant_id)
    success = plant.startup_manager.acknowledge_stale(sensor_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"No active stale reading flag for '{sensor_id}'.")
    return {"status": "acknowledged", "sensor_id": sensor_id}


@app.post("/api/verification-tokens")
def create_verification_token(
    request: VerificationTokenRequest,
    plant_id: str = Query(default="plant-a"),
):
    """Create a temporary field verification token without overriding confidence."""
    plant = plant_manager.get(plant_id)
    now = time.time()
    valid_minutes = max(1.0, min(float(request.valid_minutes), 240.0))
    valid_until = now + valid_minutes * 60.0
    token = {
        "token_id": f"{plant_id}:{request.sensor_id}:{int(now)}",
        "plant_id": plant_id,
        "sensor_id": request.sensor_id,
        "verification_type": request.verification_type,
        "created_at": now,
        "created_at_iso": datetime.utcfromtimestamp(now).isoformat() + "Z",
        "valid_until": valid_until,
        "valid_until_iso": datetime.utcfromtimestamp(valid_until).isoformat() + "Z",
        "note": request.note,
        "confidence_override": False,
        "usable_as_reference": True,
        "handover_required": True,
        "active": True,
    }
    plant.verification_tokens.append(token)
    plant.latest_handover_debt = build_handover_debt(
        plant_id=plant_id,
        incidents=plant.latest_incidents,
        confidence=list(plant.latest_confidence.values()),
        verification_tokens=plant.verification_tokens,
        confidence_debt=plant.latest_confidence_debt,
        now=now,
    )
    plant.latest_incident_timeline = _merge_incident_timeline(
        plant.latest_incident_timeline,
        _handover_debt_events(plant_id, plant.latest_handover_debt, now),
    )
    return token


@app.get("/api/verification-tokens")
def get_verification_tokens(
    plant_id: str = Query(default="plant-a"),
    active_only: bool = Query(default=False),
):
    """Return manual verification tokens. Tokens never override confidence."""
    plant = plant_manager.get(plant_id)
    now = time.time()
    tokens = []
    for token in plant.verification_tokens:
        item = dict(token)
        item["active"] = float(item.get("valid_until", 0)) > now
        item["expired"] = not item["active"]
        tokens.append(item)
    if active_only:
        tokens = [item for item in tokens if item["active"]]
    return {
        "plant_id": plant_id,
        "tokens": tokens,
        "active_count": sum(1 for item in tokens if item.get("active")),
        "confidence_override": False,
    }


# ─── REST: Shift Handover Brief (Module 6) ──────────────────────────────────

@app.post("/api/handover/generate")
async def generate_handover_brief(plant_id: str = Query(default="plant-a"), db: Session = Depends(get_db)):
    """Generate a shift handover brief from current system state."""
    plant = plant_manager.get(plant_id)
    confidence_data = list(plant.latest_confidence.values())
    if not confidence_data:
        raise HTTPException(status_code=400, detail="No sensor data available.")

    anomalies = get_recent_anomalies(db, sensor_id=None, limit=20, hours=8.0, plant_id=plant_id)

    # V2: Include prediction data in the brief
    predictions = None
    try:
        histories = {}
        for sid in plant.latest_confidence:
            histories[sid] = get_confidence_history(db, plant_id, sid, hours=24.0)
        if any(len(h) >= 10 for h in histories.values()):
            predictions = predict_all_sensors(histories)
    except Exception:
        pass

    system_state = plant.handover_generator.collect_system_state(
        confidence_data=confidence_data,
        mass_balance_state=plant.latest_mb_state,
        anomalies=anomalies,
        mode_state={
            **plant.startup_manager.to_dict(),
            "inferred_mode": plant.latest_inferred_mode.get("mode"),
            "mode_inference": plant.latest_inferred_mode,
        },
        plant_context=plant.latest_context,
        incidents=plant.latest_incidents,
    )
    system_state["incident_timeline"] = plant.latest_incident_timeline
    system_state["handover_debt"] = plant.latest_handover_debt
    system_state["verification_tokens"] = active_verification_tokens(plant.verification_tokens, time.time())
    system_state["confidence_debt"] = plant.latest_confidence_debt

    # Add predictions to state for V2 enhanced briefs
    if predictions:
        system_state["predictions"] = {
            sid: {
                "time_to_low_hours": p.get("time_to_low_hours"),
                "time_to_critical_hours": p.get("time_to_critical_hours"),
                "recommended_action": p.get("recommended_action"),
            }
            for sid, p in predictions.items()
            if p.get("time_to_low_hours") is not None
        }

    brief = await plant.handover_generator.generate_brief(system_state)

    # V2: Log the brief
    try:
        log_shift_handover(db, plant_id, brief.get("brief", ""), brief.get("source", "fallback"))
    except Exception:
        pass

    return brief


@app.get("/api/handover/latest")
def get_latest_handover(plant_id: str = Query(default="plant-a")):
    """Return the most recently generated handover brief."""
    plant = plant_manager.get(plant_id)
    brief = plant.handover_generator.latest_brief
    if brief is None:
        return {"brief": None, "message": "No handover brief has been generated yet."}
    return brief


# ─── REST: scenario control ─────────────────────────────────────────────────

@app.get("/api/handover/debt")
def get_handover_debt(plant_id: str = Query(default="plant-a")):
    """Return unresolved operational debt that must survive shift handover."""
    plant = plant_manager.get(plant_id)
    plant.latest_handover_debt = build_handover_debt(
        plant_id=plant_id,
        incidents=plant.latest_incidents,
        confidence=list(plant.latest_confidence.values()),
        verification_tokens=plant.verification_tokens,
        confidence_debt=plant.latest_confidence_debt,
        now=time.time(),
    )
    return plant.latest_handover_debt


@app.post("/api/scenario/load")
def load_scenario(scenario_path: Optional[str] = None, plant_id: str = Query(default="plant-a")):
    """Load a failure injection scenario."""
    plant = plant_manager.get(plant_id)
    DEFAULT_SCENARIO = Path(__file__).parent / "scenario.json"
    path = Path(scenario_path) if scenario_path else DEFAULT_SCENARIO
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {path}")
    plant.tag_provider.load_scenario(path)
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    return {"status": "loaded", "scenario": str(path)}


@app.post("/api/scenario/reset")
def reset_scenario(plant_id: str = Query(default="plant-a")):
    """Reset the simulator clock and state."""
    plant = plant_manager.get(plant_id)
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    return {"status": "reset"}


# ═══════════════════════════════════════════════════════════════════════════════
# V2 ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Fleet Overview (Module 9) ───────────────────────────────────────────────

@app.get("/api/fleet")
def get_fleet_overview():
    """Return fleet-level summary with risk scores for all plants."""
    return {
        "fleet": plant_manager.get_fleet_summary(),
        "plant_count": len(plant_manager.plants),
        "timestamp": time.time(),
    }


@app.get("/api/fleet/history")
def get_fleet_history(hours: float = Query(default=24.0), db: Session = Depends(get_db)):
    """Return simple fleet health trend points from confidence logs."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(ConfidenceLogModel)
        .filter(ConfidenceLogModel.timestamp >= cutoff)
        .order_by(ConfidenceLogModel.timestamp.asc())
        .limit(50000)
        .all()
    )

    buckets: dict[str, dict] = {}
    bucket_minutes = 15
    for row in rows:
        minute = (row.timestamp.minute // bucket_minutes) * bucket_minutes
        bucket_time = row.timestamp.replace(minute=minute, second=0, microsecond=0)
        key = bucket_time.isoformat()
        item = buckets.setdefault(key, {"timestamp": key, "plants": {}})
        plant_bucket = item["plants"].setdefault(row.plant_id, [])
        plant_bucket.append(row.confidence_pct)

    trend = []
    for item in buckets.values():
        point = {"timestamp": item["timestamp"]}
        for plant_id, values in item["plants"].items():
            point[plant_id] = round(sum(values) / len(values), 1) if values else None
        trend.append(point)

    return {"hours": hours, "trend": trend}


# ─── Predictive Failure Engine (Module 7) ────────────────────────────────────

@app.get("/api/predictions/{plant_id}")
def get_predictions(plant_id: str, db: Session = Depends(get_db)):
    """Return predictive failure forecasts for all sensors in a plant."""
    plant = plant_manager.get(plant_id)
    histories = {}
    for sid in plant.latest_confidence:
        histories[sid] = get_confidence_history(db, plant_id, sid, hours=24.0)

    predictions = predict_all_sensors(histories)
    return {
        "plant_id": plant_id,
        "predictions": predictions,
        "timestamp": time.time(),
    }


@app.get("/api/predictions/{plant_id}/{sensor_id}")
def get_sensor_prediction(plant_id: str, sensor_id: str, db: Session = Depends(get_db)):
    """Return predictive failure forecast for a single sensor."""
    history = get_confidence_history(db, plant_id, sensor_id, hours=24.0)
    from prediction import predict_sensor
    prediction = predict_sensor(history)
    prediction["sensor_id"] = sensor_id
    if history:
        prediction["current_confidence"] = history[-1].get("confidence_pct", 0)
        prediction["current_tier"] = history[-1].get("tier", "HIGH")
    return prediction


# ─── Natural Language Query (Module 8) ───────────────────────────────────────

@app.post("/api/query")
async def query_plant(request: QueryRequest, db: Session = Depends(get_db)):
    """Answer a natural language question about a plant."""
    plant = plant_manager.get(request.plant_id)

    # Build live state
    sensor_histories = {}
    for reading in plant.latest_readings:
        sid = reading.get("sensor_id")
        if not sid:
            continue
        sensor_histories[sid] = get_confidence_history(db, request.plant_id, sid, hours=24.0)

    live_state = {
        "readings": plant.latest_readings,
        "confidence": list(plant.latest_confidence.values()),
        "mass_balance": plant.latest_mb_state,
        "mode": {
            **plant.startup_manager.to_dict(),
            "inferred_mode": plant.latest_inferred_mode.get("mode"),
            "mode_inference": plant.latest_inferred_mode,
        },
        "incident_timeline": plant.latest_incident_timeline,
        "confidence_history": sensor_histories,
        "fleet": plant_manager.get_fleet_summary(),
    }

    anomalies = get_recent_anomalies(db, limit=20, hours=24.0, plant_id=request.plant_id)

    # Get predictions for context
    predictions = None
    try:
        histories = {}
        for sid in plant.latest_confidence:
            histories[sid] = get_confidence_history(db, request.plant_id, sid, hours=24.0)
        if any(len(h) >= 10 for h in histories.values()):
            predictions = predict_all_sensors(histories)
    except Exception:
        pass

    result = await nlquery.query_plant(
        question=request.question,
        live_state=live_state,
        anomalies=anomalies,
        predictions=predictions,
    )
    return result


# ─── Causal Graph (Module 13) ────────────────────────────────────────────────

@app.get("/api/graph/{plant_id}")
def get_causal_graph(plant_id: str):
    """Return the causal graph state with anomaly propagation chains."""
    plant = plant_manager.get(plant_id)
    return get_graph_state(plant_id, plant.latest_confidence)


@app.get("/api/trust-dependency/{plant_id}")
def get_trust_dependency_graph(plant_id: str):
    """Return simple trust dependency graph data for operator decisions."""
    plant = plant_manager.get(plant_id)
    return build_trust_dependency_graph(
        plant_id=plant_id,
        readings=plant.latest_readings,
        confidence=list(plant.latest_confidence.values()),
        mass_balance=plant.latest_mb_state,
        incidents=plant.latest_incidents,
    )


# ─── Incident Forensics & Replay (Module 10) ─────────────────────────────────

@app.get("/api/adaptive-thresholds/{plant_id}")
def get_adaptive_thresholds(
    plant_id: str,
    hours: float = Query(default=72.0),
    db: Session = Depends(get_db),
):
    """Compute learned sensor envelopes and apply them to the plant confidence engine."""
    plant = plant_manager.get(plant_id)
    envelopes = compute_adaptive_envelopes(db, plant_id, hours=hours)
    plant.confidence_engine.set_adaptive_envelopes(envelopes)
    return {
        "plant_id": plant_id,
        "hours": hours,
        "envelopes": envelopes,
        "count": len(envelopes),
        "generated_at": datetime.utcnow().isoformat(),
    }


@app.get("/api/forensics/presets")
def get_forensics_presets():
    """Return available preset incidents for replay."""
    return {
        "presets": [
            {
                "id": "texas-city",
                "name": "Texas City Incident (Demo)",
                "description": "BP Texas City refinery explosion — March 23, 2005. "
                               "LT-5100 reads 7.9ft while actual level rises to 158ft.",
                "duration_minutes": 80,
                "plant_id": "plant-a",
            },
            {
                "id": "last-8h",
                "name": "Last 8 Hours",
                "description": "Replay the last 8 hours of live data.",
                "duration_minutes": 480,
                "plant_id": None,
            },
            {
                "id": "last-24h",
                "name": "Last 24 Hours",
                "description": "Replay the last 24 hours of live data.",
                "duration_minutes": 1440,
                "plant_id": None,
            },
        ]
    }


@app.get("/api/forensics/presets/{preset_id}")
def get_forensics_preset_data(preset_id: str):
    """Return precomputed demo replay data for a named incident preset."""
    if preset_id != "texas-city":
        raise HTTPException(status_code=404, detail=f"Unknown forensics preset '{preset_id}'.")
    return _build_texas_city_replay()


@app.get("/api/forensics/{plant_id}")
def get_forensics_data(
    plant_id: str,
    hours: float = Query(default=1.0),
    db: Session = Depends(get_db),
):
    """Return historical sensor readings and confidence for forensics replay."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Sensor readings
    readings = (
        db.query(SensorReadingModel)
        .filter(SensorReadingModel.plant_id == plant_id, SensorReadingModel.timestamp >= cutoff)
        .order_by(SensorReadingModel.timestamp.asc())
        .limit(50000)
        .all()
    )

    # Confidence logs
    conf_logs = (
        db.query(ConfidenceLogModel)
        .filter(ConfidenceLogModel.plant_id == plant_id, ConfidenceLogModel.timestamp >= cutoff)
        .order_by(ConfidenceLogModel.timestamp.asc())
        .limit(50000)
        .all()
    )

    # Anomalies
    anomalies = get_recent_anomalies(db, limit=100, hours=hours, plant_id=plant_id)

    # Group readings by timestamp (rounded to nearest second)
    timeline = {}
    for r in readings:
        ts_key = r.timestamp.isoformat()[:19]  # Trim to seconds
        if ts_key not in timeline:
            timeline[ts_key] = {"timestamp": ts_key, "readings": {}, "confidence": {}}
        timeline[ts_key]["readings"][r.sensor_id] = {
            "value": r.value,
            "unit": r.unit,
            "sensor_type": r.sensor_type,
        }

    for c in conf_logs:
        ts_key = c.timestamp.isoformat()[:19]
        if ts_key in timeline:
            timeline[ts_key]["confidence"][c.sensor_id] = {
                "confidence_pct": c.confidence_pct,
                "tier": c.tier,
                "calibration_score": c.calibration_score,
                "stability_score": c.stability_score,
                "cross_sensor_score": c.cross_sensor_score,
                "plausibility_score": c.plausibility_score,
            }

    sorted_timeline = sorted(timeline.values(), key=lambda t: t["timestamp"])

    return {
        "plant_id": plant_id,
        "hours": hours,
        "data_points": len(sorted_timeline),
        "timeline": sorted_timeline,
        "anomalies": anomalies,
        "annotations": [],
        "confidence_trajectory": _confidence_trajectory_from_timeline(sorted_timeline),
        "replay": {"default_speed": 30, "available_speeds": [1, 5, 15, 30, 60]},
    }


# ─── Compliance Report (Module 11) ───────────────────────────────────────────

def _confidence_trajectory_from_timeline(timeline: list[dict]) -> dict:
    trajectory: dict[str, list] = {}
    for point in timeline:
        for sensor_id, conf in point.get("confidence", {}).items():
            trajectory.setdefault(sensor_id, []).append({
                "timestamp": point["timestamp"],
                "confidence_pct": conf.get("confidence_pct"),
                "tier": conf.get("tier"),
            })
    return trajectory


def _build_texas_city_replay() -> dict:
    """Build a compact deterministic Texas City replay for the demo."""
    start = datetime(2005, 3, 23, 12, 0, 0)
    annotations = [
        {"minute": 0, "title": "Startup begins", "body": "Raffinate splitter startup is underway."},
        {"minute": 18, "title": "Sensor drift begins", "body": "LT-5100 starts diverging from flow-implied level."},
        {"minute": 45, "title": "ConfidenceOS warning", "body": "Mass-balance and confidence checks identify unreliable level data."},
        {"minute": 64, "title": "Critical state", "body": "Tower inventory is physically inconsistent with indicated level."},
        {"minute": 80, "title": "Explosion time", "body": "Historical incident time marker."},
    ]

    timeline = []
    confidence_trajectory = {"LT-5100": [], "FI-2010": [], "FO-2020": [], "PT-3100": [], "TT-4100": [], "ZT-6100": []}
    for minute in range(0, 81, 2):
        ts = (start + timedelta(minutes=minute)).isoformat()
        actual_level = 50 + minute * 1.35
        measured_level = 50 + minute * 0.12 if minute < 18 else 52 + math.sin(minute / 6) * 0.8
        lt_conf = max(12, 94 - minute * 1.05)
        discrepancy = abs(actual_level - measured_level)

        confidence = {
            "LT-5100": {"confidence_pct": round(lt_conf, 1), "tier": "CRITICAL" if lt_conf < 20 else ("LOW" if lt_conf < 50 else ("MEDIUM" if lt_conf < 80 else "HIGH"))},
            "FI-2010": {"confidence_pct": 88, "tier": "HIGH"},
            "FO-2020": {"confidence_pct": 82 if minute < 50 else 68, "tier": "HIGH" if minute < 50 else "MEDIUM"},
            "PT-3100": {"confidence_pct": 86, "tier": "HIGH"},
            "TT-4100": {"confidence_pct": 84, "tier": "HIGH"},
            "ZT-6100": {"confidence_pct": 80 if minute < 55 else 44, "tier": "HIGH" if minute < 55 else "LOW"},
        }

        readings = {
            "LT-5100": {"value": round(measured_level, 2), "unit": "ft", "sensor_type": "level"},
            "FI-2010": {"value": round(125 + minute * 1.4, 2), "unit": "gpm", "sensor_type": "flow_in"},
            "FO-2020": {"value": round(max(20, 118 - minute * 0.8), 2), "unit": "gpm", "sensor_type": "flow_out"},
            "PT-3100": {"value": round(21 + minute * 0.18, 2), "unit": "psi", "sensor_type": "pressure"},
            "TT-4100": {"value": round(350 + minute * 0.9, 2), "unit": "F", "sensor_type": "temperature"},
            "ZT-6100": {"value": 0 if minute < 55 else 100, "unit": "%", "sensor_type": "valve"},
        }

        flags = []
        if discrepancy > 20:
            flags.append({
                "severity": "CRITICAL" if discrepancy > 55 else "WARNING",
                "message": f"Flow-implied level diverges from LT-5100 by {discrepancy:.1f} ft.",
            })

        point = {
            "timestamp": ts,
            "minute": minute,
            "readings": readings,
            "confidence": confidence,
            "mass_balance": {
                "implied_level": round(actual_level, 2),
                "measured_level": round(measured_level, 2),
                "discrepancy": round(discrepancy, 2),
                "flags": flags,
            },
        }
        timeline.append(point)
        for sensor_id, conf in confidence.items():
            confidence_trajectory[sensor_id].append({
                "timestamp": ts,
                "minute": minute,
                "confidence_pct": conf["confidence_pct"],
                "tier": conf["tier"],
            })

    return {
        "id": "texas-city",
        "name": "Texas City Incident (Demo)",
        "plant_id": "plant-a",
        "duration_minutes": 80,
        "timeline": timeline,
        "annotations": annotations,
        "confidence_trajectory": confidence_trajectory,
        "replay": {"default_speed": 30, "available_speeds": [1, 5, 15, 30, 60]},
        "counterfactual": {
            "traditional_hmi": "Shows LT-5100 level without trust context.",
            "confidenceos": "Shows confidence degradation, mass-balance divergence, and recommended verification.",
        },
    }


@app.post("/api/compliance/generate")
async def generate_compliance_report(request: ComplianceRequest, db: Session = Depends(get_db)):
    """Generate compliance report data for a plant."""
    plant = plant_manager.get(request.plant_id)
    cutoff = datetime.utcnow() - timedelta(hours=request.hours)

    # Section 1: Alarm/flag summary
    anomalies = get_recent_anomalies(db, limit=500, hours=request.hours, plant_id=request.plant_id)
    alarm_count = len(anomalies)
    alarm_by_severity = {}
    alarm_by_sensor = {}
    for a in anomalies:
        sev = a.get("severity", "INFO")
        alarm_by_severity[sev] = alarm_by_severity.get(sev, 0) + 1
        sid = a.get("sensor_id", "UNKNOWN")
        alarm_by_sensor[sid] = alarm_by_sensor.get(sid, 0) + 1

    top_10_alarms = sorted(alarm_by_sensor.items(), key=lambda x: x[1], reverse=True)[:10]

    # Section 2: Sensor reliability
    sensor_reliability = {}
    for sid in plant.latest_confidence:
        conf_history = get_confidence_history(db, request.plant_id, sid, hours=request.hours)
        if conf_history:
            tier_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "CRITICAL": 0}
            for entry in conf_history:
                t = entry.get("tier", "HIGH")
                if t in tier_counts:
                    tier_counts[t] += 1
            total = sum(tier_counts.values())
            tier_pcts = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in tier_counts.items()}
            sensor_reliability[sid] = {
                "data_points": total,
                "tier_distribution": tier_pcts,
                "current_confidence": conf_history[-1].get("confidence_pct", 100) if conf_history else 100,
                "calibration_age": plant.config["calibration_ages"].get(sid, 0),
            }

    # Section 3: Shift handover log
    from database import ShiftHandoverLog
    handover_logs = (
        db.query(ShiftHandoverLog)
        .filter(ShiftHandoverLog.plant_id == request.plant_id, ShiftHandoverLog.generated_at >= cutoff)
        .order_by(ShiftHandoverLog.generated_at.desc())
        .limit(20)
        .all()
    )
    handovers = [
        {"generated_at": h.generated_at.isoformat(), "source": h.source, "brief_text": h.brief_text[:500]}
        for h in handover_logs
    ]

    # Section 4: Mass-balance summary
    mb_anomalies = [a for a in anomalies if "mass_balance" in a.get("anomaly_type", "")]

    # Section 5: Recommendations (LLM-generated if available)
    recommendations = _generate_compliance_recommendations(
        alarm_by_severity, sensor_reliability, mb_anomalies, plant
    )

    report = {
        "plant_id": request.plant_id,
        "plant_name": plant.name,
        "report_type": request.report_type,
        "period_hours": request.hours,
        "generated_at": datetime.utcnow().isoformat(),
        "sections": {
            "alarm_summary": {
                "total_alarms": alarm_count,
                "by_severity": alarm_by_severity,
                "alarm_rate_per_hour": round(alarm_count / max(request.hours, 0.1), 2),
                "top_10_sensors": [{"sensor_id": s, "count": c} for s, c in top_10_alarms],
            },
            "sensor_reliability": sensor_reliability,
            "shift_handover_log": {"count": len(handovers), "entries": handovers},
            "mass_balance_summary": {
                "total_flags": len(mb_anomalies),
                "flags": mb_anomalies[:20],
            },
            "recommendations": recommendations,
        },
    }
    pdf_text = _format_compliance_report_text(report)
    return {
        **report,
        "report": report,
        "pdf_base64": base64.b64encode(_build_simple_pdf(pdf_text)).decode("ascii"),
        "pdf_filename": f"confidenceos_{request.plant_id}_{request.report_type}_report.pdf",
    }


def _generate_compliance_recommendations(alarm_by_severity, sensor_reliability, mb_anomalies, plant):
    """Generate maintenance recommendations based on report data."""
    recs = []

    # Find sensors needing calibration
    for sid, rel in sensor_reliability.items():
        age = rel.get("calibration_age", 0)
        if age > 60:
            recs.append({
                "priority": "critical",
                "action": f"Calibrate {sid} immediately — {age:.0f} days since last calibration.",
            })
        elif age > 40:
            recs.append({
                "priority": "high",
                "action": f"Schedule calibration for {sid} within 1 week — {age:.0f} days elapsed.",
            })

    # Flag mass-balance issues
    if len(mb_anomalies) > 5:
        recs.append({
            "priority": "high",
            "action": f"Investigate persistent mass-balance discrepancies ({len(mb_anomalies)} flags in period). Check flow sensor calibration.",
        })

    # Critical alarm count
    critical_count = alarm_by_severity.get("CRITICAL", 0)
    if critical_count > 3:
        recs.append({
            "priority": "critical",
            "action": f"{critical_count} CRITICAL events in reporting period. Root cause analysis required.",
        })

    if not recs:
        recs.append({"priority": "info", "action": "No critical issues identified. Continue routine maintenance schedule."})

    return recs


# ─── Simulation Sandbox (Module 15) ──────────────────────────────────────────

def _format_compliance_report_text(report: dict) -> str:
    sections = report.get("sections", {})
    alarm = sections.get("alarm_summary", {})
    mb = sections.get("mass_balance_summary", {})
    handover = sections.get("shift_handover_log", {})
    recommendations = sections.get("recommendations", [])

    lines = [
        "ConfidenceOS Compliance Report",
        f"Plant: {report.get('plant_name')} ({report.get('plant_id')})",
        f"Report type: {report.get('report_type')}",
        f"Period: {report.get('period_hours')} hours",
        f"Generated: {report.get('generated_at')}",
        "",
        "Alarm Summary",
        f"Total alarms: {alarm.get('total_alarms', 0)}",
        f"Alarm rate/hour: {alarm.get('alarm_rate_per_hour', 0)}",
        "",
        "Mass-Balance Summary",
        f"Total flags: {mb.get('total_flags', 0)}",
        "",
        "Shift Handover Log",
        f"Generated handovers: {handover.get('count', 0)}",
        "",
        "Recommendations",
    ]
    for rec in recommendations:
        lines.append(f"- {rec.get('priority', 'info').upper()}: {rec.get('action', '')}")
    lines.extend(["", "Digital signature: ConfidenceOS Demo Authority", "Signature status: simulated"])
    return "\n".join(lines)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(text: str) -> bytes:
    """Create a minimal single-page PDF containing plain report text."""
    lines = text.splitlines()[:42]
    content_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
    for line in lines:
        content_lines.append(f"({_pdf_escape(line[:95])}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "replace")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


@app.post("/api/sandbox/run")
def run_sandbox(request: SandboxRequest):
    """Run a simulated failure scenario without affecting live data."""
    from simulator import SensorSimulator
    from confidence import ConfidenceEngine
    from mass_balance import MassBalanceEngine

    # Create isolated instances
    sim = SensorSimulator()
    ce = ConfidenceEngine()
    mbe = MassBalanceEngine()

    # Copy calibration ages from the target plant
    plant = plant_manager.get(request.plant_id)
    for sid, age in plant.config["calibration_ages"].items():
        ce.set_calibration_age(sid, age)

    severity_factor = {"mild": 0.6, "moderate": 1.0, "severe": 1.8}.get(request.severity, 1.0)

    # Simulate the failure progression
    results = []
    duration_ticks = int(request.duration_hours * 3600 / 60)  # Sample every 60 seconds
    for i in range(min(duration_ticks, 360)):  # Cap at 360 samples
        time_hours = i * 60 / 3600
        readings = sim.tick()
        for reading in readings:
            if reading["sensor_id"] != request.sensor_id:
                continue
            if request.failure_mode == "calibration_drift":
                reading["value"] = round(reading["value"] + time_hours * 2.5 * severity_factor, 2)
                reading["failure_mode"] = "calibration_drift"
            elif request.failure_mode == "stuck_reading" and results:
                reading["value"] = results[-1]["reading"]["value"]
                reading["failure_mode"] = "stuck_reading"
            elif request.failure_mode == "sg_mismatch":
                reading["value"] = round(reading["value"] * max(0.35, 1.0 - 0.08 * time_hours * severity_factor), 2)
                reading["failure_mode"] = "sg_mismatch"
            elif request.failure_mode == "command_state_decoupling":
                reading["value"] = 0.0
                reading["failure_mode"] = "command_state_decoupling"

        confidence_results = ce.score_readings(readings)
        mb_state = mbe.update(readings)
        confidence_payload = [cr.to_dict() for cr in confidence_results]
        selected_reading = next((r for r in readings if r["sensor_id"] == request.sensor_id), None)
        selected_confidence = next((cr for cr in confidence_payload if cr["sensor_id"] == request.sensor_id), None)

        if selected_confidence and selected_reading:
            results.append({
                "time_hours": round(time_hours, 2),
                "reading": selected_reading,
                "confidence": selected_confidence,
                "confidence_pct": selected_confidence["confidence_pct"],
                "tier": selected_confidence["tier"],
                "reasons": selected_confidence["reasons"][:2],
                "mass_balance": mb_state.to_dict(),
                "flags": [f.to_dict() for f in mb_state.flags],
                "all_confidence": confidence_payload,
            })

        # Simulate degradation
        current_age = ce.calibration_ages.get(request.sensor_id, 0)
        if request.failure_mode == "calibration_drift":
            rate = {"mild": 0.5, "moderate": 1.0, "severe": 2.0}.get(request.severity, 1.0)
            ce.set_calibration_age(request.sensor_id, current_age + rate * (60 / 86400))

    return {
        "sensor_id": request.sensor_id,
        "failure_mode": request.failure_mode,
        "severity": request.severity,
        "duration_hours": request.duration_hours,
        "sample_count": len(results),
        "results": results,
    }


# ─── Health check ────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    """Basic health check."""
    plant_a = plant_manager.get("plant-a")
    return {
        "status": "ok",
        "version": "2.0.0",
        "uptime_seconds": round(plant_a.tag_provider.elapsed(), 1),
        "tick_count": plant_a.tag_provider.tick_count,
        "active_connections": len(active_connections),
        "plants": len(plant_manager.plants),
        "plant_loops": _plant_loop_status,
        "db_status": "writing" if any(s.get("status") == "ok" for s in _plant_loop_status.values()) else "warming_up",
        "modules": {
            "sensor_simulator": "active",
            "tag_provider": "active",
            "read_only_trust_layer": "active",
            "asset_model": "active",
            "confidence_engine": "active",
            "confidence_explainability": "active",
            "assumption_register": "active",
            "mass_balance_engine": "active",
            "startup_manager": "active",
            "mode_inference": "active",
            "handover_generator": "active",
            "prediction_engine": "active",
            "nlquery_engine": "active",
            "causal_graph": "active",
            "adaptive_thresholds": "active",
            "advisory_engine": "active",
            "incident_timeline": "active",
            "score_sensitivity": "active",
            "verification_tokens": "active",
            "handover_debt": "active",
            "confidence_debt": "active",
            "trust_dependency_graph": "active",
            "compliance_pdf": "active",
            "forensics_replay": "active",
            "sandbox": "active",
            "fleet_manager": "active",
        },
    }
