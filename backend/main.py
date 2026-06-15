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
  - GET /api/fleet — instrument integrity overview for all plants
  - GET /api/predictions/{plant_id} — confidence degradation forecasts
  - POST /api/query — grounded operator explanation
  - GET /api/graph/{plant_id} — causal graph state
  - GET /api/forensics/{plant_id} — historical data for replay
  - GET /api/forensics/presets — available preset incidents
  - POST /api/compliance/generate — compliance report data
"""

import asyncio
import base64
import json
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    get_verification_audit,
)
from plants import PlantManager, UnknownPlantError
from mass_balance import DEFAULT_TOLERANCE
from prediction import predict_all_sensors
from causal_graph import get_graph_state
from adaptive_thresholds import compute_adaptive_envelopes
from advisory import detect_plant_context, build_incidents, build_timeline_events
from assumptions import build_confidence_explanation, load_assumptions
from asset_model import load_asset_model, mass_balance_validation
from model_graph import get_assets, get_model_graph, get_navigation, get_signals
from screen_generator import equipment_manifest
from decision_integrity import (
    active_verification_tokens,
    annotate_incidents_for_handover,
    build_handover_debt,
    build_score_sensitivity,
    build_trust_dependency_graph,
    normalize_verification_task,
    update_confidence_debt,
)
from verification_service import (
    create_task as create_verification_task,
    list_tasks as list_verification_tasks,
    sync_auto_tasks,
    transition_task as transition_verification_task,
)
from studio_service import (
    assign_template as studio_assign_template,
    auto_map as studio_auto_map,
    approve_raw_tag as studio_approve_raw_tag,
    current_build as studio_current_build,
    diff as studio_diff,
    generate_preview as studio_generate_preview,
    ignore_raw_tag as studio_ignore_raw_tag,
    import_arbitrary_tags as studio_import_arbitrary_tags,
    imported_signals as studio_imported_signals,
    keep_raw_tag_blocking as studio_keep_raw_tag_blocking,
    mapping_court_detail as studio_mapping_court_detail,
    mapping_court_items as studio_mapping_court,
    manual_map_raw_tag as studio_manual_map_raw_tag,
    persisted_build_artifacts as studio_persisted_build_artifacts,
    persisted_import_batches as studio_persisted_import_batches,
    publish as studio_publish,
    reset as studio_reset,
    runtime_manifest as studio_runtime_manifest,
    run_compiler_build as studio_run_compiler_build,
    select_asset_model as studio_select_asset_model,
    studio_overview,
    suggest_template_for_asset as studio_suggest_template,
    template_tests as studio_template_tests,
    update_template_mutation as studio_update_template_mutation,
    validation as studio_validation,
)
from template_library import get_template_catalog
from shift_channel import add_note as add_shift_note, build_shift_channel, reset_notes as reset_shift_notes
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
SCENARIO_DIR = Path(__file__).parent
ALLOWED_SCENARIOS = {"scenario.json", "scenario_b.json", "scenario_c.json"}


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

class VerificationEvidenceRequest(BaseModel):
    method: Optional[str] = None
    field_reading_value: Optional[float] = None
    field_reading_unit: Optional[str] = None
    technician_note: Optional[str] = None
    attachment_ref: Optional[str] = None

class VerificationTaskUpdateRequest(BaseModel):
    task_id: str
    state: str
    accepted_by: Optional[str] = None
    note: str = ""
    actor: Optional[str] = None        # client-supplied identity (no real auth yet)
    actor_role: Optional[str] = None   # Operator / Maintenance / Engineer / Manager / Auditor
    evidence_note: str = ""            # required for FIELD_CHECK_DONE and ACCEPTED
    evidence: Optional[VerificationEvidenceRequest] = None

class StudioTemplateAssignmentRequest(BaseModel):
    asset_id: str
    template_id: str
    approved: bool = True

class StudioGenerateRequest(BaseModel):
    role: str = "Engineer"
    context: str = "auto"

class StudioRawTagResolutionRequest(BaseModel):
    raw_tag: str
    reason: str = ""

class StudioManualMapRequest(BaseModel):
    raw_tag: str
    canonical_tag: str
    asset_id: str
    signal_role: str
    reason: str

class StudioAssetModelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_key: str

class StudioTemplateMutationRequest(BaseModel):
    require_manual_verification_when_level_quarantined: bool = False

class ShiftNoteRequest(BaseModel):
    plant_id: str = "plant-a"
    author: str = "Operator"
    message: str


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
def _configured_cors_origins() -> list[str]:
    configured = os.getenv(
        "CONFIDENCEOS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)


# ─── Background plant tick loop ─────────────────────────────────────────────

@app.exception_handler(UnknownPlantError)
async def unknown_plant_handler(request: Request, exc: UnknownPlantError):
    plant_id = exc.args[0] if exc.args else "unknown"
    return JSONResponse(
        status_code=404,
        content={
            "detail": f"Unknown plant_id '{plant_id}'",
            "known_plants": sorted(plant_manager.get_all().keys()),
        },
    )


async def _plant_tick_loop(plant_id: str, plant):
    """Background loop that ticks each plant at 1 Hz and caches state."""
    db = next(get_db())
    tick_count = 0

    try:
        while True:
            try:
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

                # Update mass-balance
                mb_state = plant.mass_balance_engine.update(readings)
                plant.latest_mb_state = mb_state.to_dict()
                confidence_data = _derive_trust_states(confidence_data, readings, plant.latest_mb_state)

                # Update cached confidence after trust quarantine/substitution is derived.
                for payload in confidence_data:
                    plant.latest_confidence[payload["sensor_id"]] = payload

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
                plant.verification_tokens = sync_auto_tasks(
                    db,
                    plant_id=plant_id,
                    incidents=plant.latest_incidents,
                    confidence=confidence_data,
                    plant_context=plant.latest_context,
                    now=now,
                )
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
            except Exception as e:
                db.rollback()
                print(f"[PlantTick] Error in {plant_id}: {e}")
                _plant_loop_status[plant_id] = {
                    "status": "error",
                    "last_tick": time.time(),
                    "tick_count": getattr(plant.tag_provider, "tick_count", 0),
                    "last_error": str(e),
                }
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        db.close()
    except Exception as e:
        print(f"[PlantTick] Fatal error in {plant_id}: {e}")
        _plant_loop_status[plant_id] = {
            "status": "fatal",
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


def _derive_trust_states(confidence: list[dict], readings: list[dict], mass_balance: dict | None) -> list[dict]:
    """Derive read-only trust quarantine state from confidence and mass-balance evidence."""
    readings_by_id = {item.get("sensor_id"): item for item in readings or []}
    flags = (mass_balance or {}).get("flags", [])
    contradiction_active = any(flag.get("severity") in ("WARNING", "CRITICAL") for flag in flags)
    by_id = {item.get("sensor_id"): item for item in confidence if item.get("sensor_id")}
    relationship = mass_balance_validation()
    validated_tag = relationship.get("validated_tag")
    source_tags = relationship.get("source_tags", [])
    inferred_variable = relationship.get("inferred_variable") or f"{validated_tag or 'signal'}_substitute"
    validated_confidence = by_id.get(validated_tag)
    level_quarantined = bool(
        validated_confidence
        and validated_confidence.get("tier") in ("LOW", "CRITICAL")
        and contradiction_active
    )
    flow_substitute_valid = all(
        by_id.get(tag, {}).get("tier") in ("HIGH", "MEDIUM")
        and readings_by_id.get(tag) is not None
        for tag in source_tags
    ) if source_tags else False

    decorated = []
    for item in confidence:
        sensor_id = item.get("sensor_id")
        tier = item.get("tier")
        reading_available = readings_by_id.get(sensor_id) is not None
        trust_state = "TRUSTED"
        trust_reason = "Confidence and availability support normal use."
        substitute_for = None
        decision_basis_allowed = True
        quarantine_relationship_id = None

        if not reading_available:
            trust_state = "UNAVAILABLE"
            trust_reason = "No current reading is available for this tag."
            decision_basis_allowed = False
        elif sensor_id == validated_tag and level_quarantined:
            trust_state = "QUARANTINED"
            trust_reason = "Level confidence is LOW/CRITICAL while mass-balance contradiction is active."
            decision_basis_allowed = False
            quarantine_relationship_id = relationship.get("id")
        elif sensor_id in source_tags and level_quarantined and flow_substitute_valid:
            trust_state = "SUBSTITUTED"
            trust_reason = "Mass-balance source tag is valid enough to support the inferred level substitute."
            substitute_for = inferred_variable
            quarantine_relationship_id = relationship.get("id")
        elif tier in ("LOW", "CRITICAL"):
            trust_state = "DEGRADED"
            trust_reason = "Confidence tier is below operator-trusted range."
            decision_basis_allowed = False
        elif tier == "MEDIUM":
            trust_state = "DEGRADED"
            trust_reason = "Confidence tier requires evidence review before use as primary basis."

        decorated.append({
            **item,
            "trust_state": trust_state,
            "trust_reason": trust_reason,
            "decision_basis_allowed": decision_basis_allowed,
            "substitute_for": substitute_for,
            "quarantine_relationship_id": quarantine_relationship_id,
            "quarantine_active": trust_state == "QUARANTINED",
        })
    return decorated


def _runtime_live_state(plant_id: str, plant) -> dict:
    """Collect frontend-friendly live state for generated Runtime manifests."""
    confidence = list(plant.latest_confidence.values())
    if confidence and any("trust_state" not in item for item in confidence):
        confidence = _derive_trust_states(confidence, plant.latest_readings, plant.latest_mb_state)
    now = time.time()
    verification_tasks = [normalize_verification_task(task, now) for task in plant.verification_tokens or []]
    active_tasks = active_verification_tokens(plant.verification_tokens, now)
    return {
        "plant_id": plant_id,
        "readings": plant.latest_readings,
        "confidence": confidence,
        "mass_balance": plant.latest_mb_state,
        "mode": plant.latest_mode_payload,
        "plant_context": plant.latest_context,
        "incidents": plant.latest_incidents,
        "incident_timeline": plant.latest_incident_timeline,
        "verification_tokens": active_tasks,
        "verification_tasks": verification_tasks,
        "handover_debt": plant.latest_handover_debt,
        "confidence_debt": plant.latest_confidence_debt,
    }


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
    try:
        plant = plant_manager.get(plant_id)
    except UnknownPlantError:
        await websocket.send_json({
            "type": "error",
            "detail": f"Unknown plant_id '{plant_id}'",
            "known_plants": sorted(plant_manager.get_all().keys()),
        })
        await websocket.close(code=1008)
        return
    active_connections.append(websocket)

    try:
        while True:
            now = time.time()
            readings = plant.latest_readings
            confidence_data = list(plant.latest_confidence.values())
            if confidence_data and any("trust_state" not in item for item in confidence_data):
                confidence_data = _derive_trust_states(confidence_data, readings, plant.latest_mb_state)
            stale_flags = plant.startup_manager.check_stale_readings(readings, now) if readings else []
            verification_tasks = [normalize_verification_task(task, now) for task in plant.verification_tokens or []]
            active_tasks = active_verification_tokens(plant.verification_tokens, now)

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
                "verification_tokens": active_tasks,
                "verification_tasks": verification_tasks,
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
            "handover, and decision-freeze metadata as a read-only trust layer beside "
            "existing HMI/DCS control layers. It does not write commands to ABB-class systems."
        ),
        "active_providers": {
            plant_id: plant.tag_provider.to_dict()
            for plant_id, plant in plant_manager.get_all().items()
        },
        "available_providers": provider_catalog(),
        "asset_model_id": asset_model.get("model_id"),
        "equipment_id": asset_model.get("equipment", {}).get("equipment_id"),
    }


@app.get("/api/model/graph")
def get_model_graph_endpoint():
    """Return the asset/signal graph that drives generated HMI screens."""
    return get_model_graph()


@app.get("/api/model/assets")
def get_model_assets():
    """Return model assets: plant, area, unit, module, equipment."""
    return {"assets": get_assets(), "count": len(get_assets())}


@app.get("/api/model/signals")
def get_model_signals():
    """Return imported and mapped process signals."""
    signals = get_signals()
    return {"signals": signals, "count": len(signals), "source": "asset_model.json"}


@app.get("/api/templates")
def get_templates():
    """Return reusable signal/equipment templates and policies."""
    return get_template_catalog()


@app.get("/api/screens/generated")
def get_generated_screens(
    role: str = Query(default="Operator"),
    context: str = Query(default="auto"),
    plant_id: str = Query(default="plant-a"),
):
    """Return latest published Runtime manifest hydrated with live read-only state."""
    plant = plant_manager.get(plant_id)
    return studio_runtime_manifest(
        role=role,
        context=context,
        live_state=_runtime_live_state(plant_id, plant),
    )


@app.get("/api/runtime/navigation")
def get_runtime_navigation():
    """Return semantic plant navigation for Runtime."""
    return {"navigation": get_navigation(), "semantic_zoom": ["plant", "area", "unit", "module", "equipment", "signal"]}


@app.get("/api/runtime/situations")
def get_runtime_situations(plant_id: str = Query(default="plant-a")):
    """Return current abnormal situations and operating-basis contracts."""
    plant = plant_manager.get(plant_id)
    return {
        "plant_id": plant_id,
        "situations": plant.latest_incidents,
        "count": len(plant.latest_incidents),
        "context": plant.latest_context,
    }


@app.get("/api/runtime/equipment/{equipment_id}")
def get_runtime_equipment(
    equipment_id: str,
    role: str = Query(default="Operator"),
    plant_id: str = Query(default="plant-a"),
):
    """Return generated equipment faceplate manifest."""
    plant = plant_manager.get(plant_id)
    faceplate = equipment_manifest(
        equipment_id,
        role,
        live_state=_runtime_live_state(plant_id, plant),
        assignments=studio_overview()["state"].get("assignments", []),
    )
    if not faceplate:
        raise HTTPException(status_code=404, detail=f"Equipment not found: {equipment_id}")
    return faceplate


@app.get("/api/studio/imported-signals")
def get_studio_imported_signals():
    """Return current imported simulator/model signals for Studio."""
    return studio_imported_signals()


@app.post("/api/studio/asset-model")
def post_studio_asset_model(request: StudioAssetModelRequest):
    """Switch the active metadata model used by the read-only HMI Compiler."""
    return studio_select_asset_model(request.model_key)


@app.post("/api/studio/template-mutation")
def post_studio_template_mutation(request: StudioTemplateMutationRequest):
    """Apply the controlled vessel-template mutation demo toggle."""
    return studio_update_template_mutation(request.require_manual_verification_when_level_quarantined)


@app.get("/api/studio/build")
def get_studio_build():
    """Return the latest HMI Compiler build artifact without mutating Studio state."""
    return studio_current_build()


@app.post("/api/studio/build/run")
def post_studio_build_run():
    """Run the read-only HMI Compiler pipeline and store the build artifact."""
    return studio_run_compiler_build()


@app.get("/api/studio/build/artifacts")
def get_studio_build_artifacts(
    model_key: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return immutable SQLite receipts for recent HMI Compiler builds."""
    return studio_persisted_build_artifacts(model_key=model_key, limit=limit)


@app.get("/api/studio/import-batches")
def get_studio_import_batches(
    model_key: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return durable raw-tag import batch receipts used by compiler builds."""
    return studio_persisted_import_batches(model_key=model_key, limit=limit)


@app.get("/api/studio/template-tests")
def get_studio_template_tests():
    """Return deterministic template smoke-test results for Studio."""
    return studio_template_tests()


@app.get("/api/studio/mapping-court")
def get_studio_mapping_court():
    """Return evidence-ledger rows for imported tag mapping suggestions."""
    return studio_mapping_court()


@app.get("/api/studio/mapping-court/{raw_tag:path}")
def get_studio_mapping_court_detail(raw_tag: str):
    """Return one evidence-ledger row for an imported raw tag."""
    return studio_mapping_court_detail(raw_tag)


@app.post("/api/studio/mapping-court/approve")
def post_studio_mapping_approve(request: StudioRawTagResolutionRequest):
    """Approve a deterministic raw-tag mapping. Engineer approval remains explicit."""
    result = studio_approve_raw_tag(request.raw_tag)
    if result.get("status") == "not_approved":
        raise HTTPException(status_code=409, detail=result)
    return result


@app.post("/api/studio/mapping-court/ignore")
def post_studio_mapping_ignore(request: StudioRawTagResolutionRequest):
    """Ignore an imported raw tag with an engineering reason."""
    result = studio_ignore_raw_tag(request.raw_tag, request.reason)
    if result.get("status") == "not_ignored":
        raise HTTPException(status_code=422, detail=result)
    return result


@app.post("/api/studio/mapping-court/manual-map")
def post_studio_mapping_manual_map(request: StudioManualMapRequest):
    """Manually bind an imported raw tag to an active-model signal with an engineering reason."""
    result = studio_manual_map_raw_tag(
        request.raw_tag,
        request.canonical_tag,
        request.asset_id,
        request.signal_role,
        request.reason,
    )
    if result.get("status") == "not_mapped":
        raise HTTPException(status_code=422, detail=result)
    return result


@app.post("/api/studio/mapping-court/keep-blocking")
def post_studio_mapping_keep_blocking(request: StudioRawTagResolutionRequest):
    """Keep an imported raw tag unresolved so publish remains blocked."""
    return studio_keep_raw_tag_blocking(request.raw_tag)


@app.post("/api/studio/auto-map")
async def post_studio_auto_map():
    """Generate mapping suggestions with optional AI explanation. Approval is still required."""
    return await studio_auto_map()


@app.post("/api/studio/import-tags")
async def post_studio_import_tags(request: dict):
    """
    Accept a pasted or uploaded arbitrary tag list and route through AI parse → Mapping Court.

    Body: {"tags": ["RAW_TAG_1", "RAW_TAG_2", ...]}

    Every AI-proposed binding is returned for engineer review. Nothing is
    auto-approved or published — all proposals must go through the Mapping
    Court before the build gate.
    """
    raw_tags = request.get("tags", [])
    if not isinstance(raw_tags, list):
        raise HTTPException(status_code=422, detail="'tags' must be a list of strings.")
    cleaned = [str(t).strip() for t in raw_tags if str(t).strip()]
    if not cleaned:
        raise HTTPException(status_code=422, detail="No non-empty tags provided.")
    return await studio_import_arbitrary_tags(cleaned)


@app.post("/api/studio/suggest-template")
async def post_studio_suggest_template(request: dict):
    """
    Given a plain-English asset description, Claude proposes a template from
    the real template library. Compiler validates; engineer approves.

    Body: {"description": "A centrifugal pump with discharge pressure and vibration monitoring"}
    """
    description = (request.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="'description' is required.")
    return await studio_suggest_template(description)


@app.post("/api/studio/assign-template")
def post_studio_assign_template(request: StudioTemplateAssignmentRequest):
    """Approve or update an asset/template assignment."""
    return studio_assign_template(request.asset_id, request.template_id, approved=request.approved)


@app.post("/api/studio/generate")
def post_studio_generate(request: StudioGenerateRequest | None = None):
    """Generate a Studio preview manifest without publishing control changes."""
    payload = request or StudioGenerateRequest()
    return studio_generate_preview(role=payload.role, context=payload.context)


@app.post("/api/studio/publish")
def post_studio_publish():
    """Publish generated metadata to Runtime manifest state. This remains read-only to controls."""
    result = studio_publish()
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result)
    return result


@app.post("/api/studio/reset")
def post_studio_reset():
    """Reset Studio state to demo defaults."""
    return studio_reset()


@app.get("/api/studio/validation")
def get_studio_validation():
    """Return template and mapping validation warnings."""
    return studio_validation()


@app.get("/api/studio/diff")
def get_studio_diff():
    """Return Studio changes since demo defaults."""
    return studio_diff()


@app.get("/api/studio")
def get_studio_overview():
    """Return consolidated Studio state for the low-code engineering workspace."""
    return studio_overview()


@app.get("/api/shift-channel")
def get_shift_channel(plant_id: str = Query(default="plant-a"), db: Session = Depends(get_db)):
    """Return persistent shift channel with pinned unresolved operating debt."""
    plant = plant_manager.get(plant_id)
    plant.verification_tokens = list_verification_tasks(db, plant_id=plant_id, include_closed=True)
    plant.latest_handover_debt = build_handover_debt(
        plant_id=plant_id,
        incidents=plant.latest_incidents,
        confidence=list(plant.latest_confidence.values()),
        verification_tokens=plant.verification_tokens,
        confidence_debt=plant.latest_confidence_debt,
        now=time.time(),
    )
    return build_shift_channel(plant_id, plant)


@app.post("/api/shift-channel/note")
def post_shift_channel_note(request: ShiftNoteRequest, db: Session = Depends(get_db)):
    """Add an operator note to the persistent shift channel."""
    note = add_shift_note(request.plant_id, request.author, request.message)
    plant = plant_manager.get(request.plant_id)
    plant.verification_tokens = list_verification_tasks(db, plant_id=request.plant_id, include_closed=True)
    return {
        "note": note,
        "channel": build_shift_channel(request.plant_id, plant),
    }


@app.post("/api/shift-channel/reset")
def post_shift_channel_reset():
    """Reset demo shift-channel notes; operational debt is rebuilt from live state."""
    return {"status": "reset", "state": reset_shift_notes()}


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


# ── Verification workflow lifecycle rules ───────────────────────────────────
# Legal transition graph: a task can only advance along this path. EXPIRED is
# reachable from any active state. This makes the workflow a real, guarded state
# machine rather than free-form state writes.
VERIFICATION_TRANSITIONS = {
    "REQUESTED": {"ASSIGNED", "EXPIRED"},
    "ASSIGNED": {"FIELD_CHECK_DONE", "EXPIRED"},
    "FIELD_CHECK_DONE": {"ACCEPTED", "EXPIRED"},
    "ACCEPTED": set(),   # terminal
    "EXPIRED": set(),    # terminal
}
# Transitions that must cite an evidence note (field work / engineer acceptance).
VERIFICATION_EVIDENCE_REQUIRED = {"FIELD_CHECK_DONE", "ACCEPTED"}
# Light, advisory role scoping (no real auth — actor_role is client-supplied).
VERIFICATION_ROLE_SCOPE = {
    "ASSIGNED": {"Maintenance", "Engineer", "Manager"},
    "FIELD_CHECK_DONE": {"Maintenance", "Engineer"},
    "ACCEPTED": {"Engineer", "Manager"},
    "EXPIRED": {"Operator", "Maintenance", "Engineer", "Manager", "Auditor"},
}


@app.post("/api/verification-tokens")
def create_verification_token(
    request: VerificationTokenRequest,
    plant_id: str = Query(default="plant-a"),
    db: Session = Depends(get_db),
):
    """Create a temporary field verification token without overriding confidence."""
    plant = plant_manager.get(plant_id)
    now = time.time()
    token = create_verification_task(
        db,
        plant_id=plant_id,
        sensor_id=request.sensor_id,
        verification_type=request.verification_type,
        valid_minutes=request.valid_minutes,
        note=request.note,
        source="manual",
    )
    plant.verification_tokens = list_verification_tasks(db, plant_id=plant_id, include_closed=True)
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


@app.post("/api/verification-tasks/state")
def update_verification_task_state(
    request: VerificationTaskUpdateRequest,
    plant_id: str = Query(default="plant-a"),
    db: Session = Depends(get_db),
):
    """
    Advance a field verification task along its guarded lifecycle.

    Enforces: a legal transition graph, an evidence note for field-check / accept,
    and (advisory) role scoping. Captures owner + timestamp per state and writes an
    immutable audit event. Never changes confidence and never writes a control.
    """
    plant = plant_manager.get(plant_id)
    now = time.time()
    updated = transition_verification_task(
        db,
        plant_id=plant_id,
        task_id=request.task_id,
        to_state=request.state,
        actor=request.actor or request.accepted_by,
        actor_role=request.actor_role,
        evidence_note=request.evidence_note or request.note,
        evidence=request.evidence.model_dump(exclude_none=True) if request.evidence else None,
    )
    plant.verification_tokens = list_verification_tasks(db, plant_id=plant_id, include_closed=True)
    plant.latest_handover_debt = build_handover_debt(
        plant_id=plant_id,
        incidents=plant.latest_incidents,
        confidence=list(plant.latest_confidence.values()),
        verification_tokens=plant.verification_tokens,
        confidence_debt=plant.latest_confidence_debt,
        now=now,
    )
    return {"status": "updated", "task": updated, "handover_debt": plant.latest_handover_debt}

    allowed = {"REQUESTED", "ASSIGNED", "FIELD_CHECK_DONE", "ACCEPTED", "REJECTED", "EXPIRED"}
    state = request.state.upper()
    if state not in allowed:
        raise HTTPException(status_code=400, detail=f"state must be one of {sorted(allowed)}")

    # Evidence note is mandatory for field-check completion and engineer acceptance.
    evidence_note = (request.evidence_note or request.note or "").strip()
    if state in VERIFICATION_EVIDENCE_REQUIRED and not evidence_note:
        raise HTTPException(
            status_code=422,
            detail=f"An evidence note is required to move a task to {state}.",
        )

    # Advisory role scoping (no real auth — actor_role is client-supplied).
    actor_role = request.actor_role
    allowed_roles = VERIFICATION_ROLE_SCOPE.get(state)
    if allowed_roles and actor_role and actor_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{actor_role}' may not perform transition to {state}. Allowed: {sorted(allowed_roles)}",
        )

    plant = plant_manager.get(plant_id)
    now = time.time()
    now_iso = datetime.utcfromtimestamp(now).isoformat() + "Z"
    actor = request.actor or request.accepted_by
    updated = None
    from_state = None
    tasks = []
    for token in plant.verification_tokens:
        task = normalize_verification_task(token, now)
        if task.get("task_id") == request.task_id or task.get("token_id") == request.task_id:
            from_state = task.get("state")
            # Guard against illegal jumps. Allow no-op re-assert of the same state.
            legal = VERIFICATION_TRANSITIONS.get(from_state, set())
            if state != from_state and state not in legal:
                raise HTTPException(
                    status_code=400,
                    detail=f"Illegal transition {from_state} -> {state}. Legal next states: {sorted(legal)}",
                )
            history = list(task.get("history", []))
            history.append({
                "from_state": from_state,
                "to_state": state,
                "actor": actor,
                "actor_role": actor_role,
                "evidence_note": evidence_note or None,
                "at": now,
                "at_iso": now_iso,
            })
            task["state"] = state
            task["history"] = history
            task["note"] = evidence_note or task.get("note")
            # Per-state ownership stamps.
            if state == "ASSIGNED":
                task["assigned_to"] = actor
                task["assigned_at"] = now
            elif state == "FIELD_CHECK_DONE":
                task["field_checked_by"] = actor
                task["field_checked_at"] = now
            elif state == "ACCEPTED":
                task["accepted_by"] = actor or request.accepted_by
                task["accepted_at"] = now
            task["handover_required"] = state not in ("ACCEPTED", "EXPIRED")
            task["active"] = float(task.get("valid_until", 0)) > now and state not in ("ACCEPTED", "EXPIRED")
            task["expired"] = state == "EXPIRED" or float(task.get("valid_until", 0)) <= now
            task["updated_at"] = now
            task["updated_at_iso"] = now_iso
            updated = task
        tasks.append(task)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No verification task '{request.task_id}'")

    plant.verification_tokens = tasks
    # Immutable audit trail row for this transition.
    log_verification_event(
        db,
        plant_id=plant_id,
        task_id=updated.get("task_id"),
        to_state=state,
        from_state=from_state,
        sensor_id=updated.get("sensor_id"),
        actor=actor,
        actor_role=actor_role,
        evidence_note=evidence_note or None,
    )
    plant.latest_handover_debt = build_handover_debt(
        plant_id=plant_id,
        incidents=plant.latest_incidents,
        confidence=list(plant.latest_confidence.values()),
        verification_tokens=plant.verification_tokens,
        confidence_debt=plant.latest_confidence_debt,
        now=now,
    )
    return {"status": "updated", "task": updated, "handover_debt": plant.latest_handover_debt}


@app.get("/api/verification-tasks/audit")
def get_verification_task_audit(
    plant_id: str = Query(default="plant-a"),
    task_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return the immutable, time-ordered verification audit trail (optionally for one task)."""
    plant_manager.get(plant_id)  # validates plant_id → 404 if unknown
    events = get_verification_audit(db, plant_id, task_id=task_id)
    return {
        "plant_id": plant_id,
        "task_id": task_id,
        "events": events,
        "count": len(events),
        "note": "Immutable append-only audit trail. Actor identity is client-supplied (no auth yet).",
    }


@app.get("/api/verification-tasks/{task_id:path}")
def get_verification_task_detail(
    task_id: str,
    plant_id: str = Query(default="plant-a"),
    db: Session = Depends(get_db),
):
    """Return one durable field-verification task by id."""
    plant_manager.get(plant_id)
    tasks = list_verification_tasks(db, plant_id=plant_id, include_closed=True)
    for task in tasks:
        if task.get("task_id") == task_id or task.get("token_id") == task_id:
            return {"plant_id": plant_id, "task": task}
    raise HTTPException(status_code=404, detail=f"No verification task '{task_id}'")


@app.get("/api/verification-tokens")
def get_verification_tokens(
    plant_id: str = Query(default="plant-a"),
    active_only: bool = Query(default=False),
    include_closed: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Return compatibility token-shaped field verification tasks. Tasks never override confidence."""
    plant_manager.get(plant_id)
    tokens = list_verification_tasks(
        db,
        plant_id=plant_id,
        active_only=active_only,
        include_closed=include_closed,
    )
    return {
        "plant_id": plant_id,
        "tokens": tokens,
        "active_count": sum(1 for item in tokens if item.get("active")),
        "confidence_override": False,
    }


@app.get("/api/verification-tasks")
def get_verification_tasks(
    plant_id: str = Query(default="plant-a"),
    state: Optional[str] = Query(default=None),
    include_closed: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Return durable field-verification tasks, including closed tasks by default."""
    plant_manager.get(plant_id)
    tasks = list_verification_tasks(db, plant_id=plant_id, include_closed=include_closed)
    if state:
        tasks = [task for task in tasks if task.get("state") == state.upper()]
    return {
        "plant_id": plant_id,
        "tasks": tasks,
        "count": len(tasks),
        "active_count": sum(1 for item in tasks if item.get("active")),
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
def get_handover_debt(plant_id: str = Query(default="plant-a"), db: Session = Depends(get_db)):
    """Return unresolved operational debt that must survive shift handover."""
    plant = plant_manager.get(plant_id)
    plant.verification_tokens = list_verification_tasks(db, plant_id=plant_id, include_closed=True)
    plant.latest_handover_debt = build_handover_debt(
        plant_id=plant_id,
        incidents=plant.latest_incidents,
        confidence=list(plant.latest_confidence.values()),
        verification_tokens=plant.verification_tokens,
        confidence_debt=plant.latest_confidence_debt,
        now=time.time(),
    )
    return plant.latest_handover_debt


def _resolve_scenario_path(scenario_path: Optional[str]) -> Path:
    if not scenario_path:
        scenario_name = "scenario.json"
    else:
        candidate = Path(scenario_path)
        if candidate.is_absolute() or ".." in candidate.parts or candidate.name != str(candidate):
            raise HTTPException(status_code=400, detail="Scenario path must be a known demo scenario filename.")
        scenario_name = candidate.name
    if scenario_name not in ALLOWED_SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown demo scenario: {scenario_name}")
    path = SCENARIO_DIR / scenario_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Scenario file not found: {scenario_name}")
    return path


@app.post("/api/scenario/load")
def load_scenario(scenario_path: Optional[str] = None, plant_id: str = Query(default="plant-a")):
    """Load a failure injection scenario."""
    plant = plant_manager.get(plant_id)
    path = _resolve_scenario_path(scenario_path)
    plant.tag_provider.load_scenario(path)
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    return {"status": "loaded", "scenario": path.name}


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

# ─── Instrument Integrity Overview (Module 9) ────────────────────────────────

@app.get("/api/fleet")
def get_fleet_overview():
    """Return instrument integrity summary for all plants."""
    return {
        "fleet": plant_manager.get_fleet_summary(),
        "plant_count": len(plant_manager.plants),
        "timestamp": time.time(),
    }


@app.get("/api/fleet/history")
def get_fleet_history(hours: float = Query(default=24.0), db: Session = Depends(get_db)):
    """Return simple instrument integrity trend points from confidence logs."""
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


# ─── Confidence Degradation Forecast (Module 7) ──────────────────────────────

@app.get("/api/predictions/{plant_id}")
def get_predictions(plant_id: str, db: Session = Depends(get_db)):
    """Return confidence degradation forecasts for all sensors in a plant."""
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
    """Return confidence degradation forecast for a single sensor."""
    history = get_confidence_history(db, plant_id, sensor_id, hours=24.0)
    from prediction import predict_sensor
    prediction = predict_sensor(history)
    prediction["sensor_id"] = sensor_id
    if history:
        prediction["current_confidence"] = history[-1].get("confidence_pct", 0)
        prediction["current_tier"] = history[-1].get("tier", "HIGH")
    return prediction


# ─── Grounded Operator Explanation (Module 8) ────────────────────────────────

@app.post("/api/query")
async def query_plant(request: QueryRequest, db: Session = Depends(get_db)):
    """Answer a grounded operator question about a plant."""
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
        {"minute": 12, "title": "Confidence degraded", "body": "LT-5100 confidence falls below normal operating trust."},
        {"minute": 18, "title": "Mass-balance divergence detected", "body": "FI-2010 and FO-2020 imply rising inventory while LT-5100 remains low."},
        {"minute": 24, "title": "Action contract created", "body": "Do not use LT-5100 as the sole level reference; verify locally before feed increase."},
        {"minute": 30, "title": "Decision freeze created", "body": "Feed and load increase decisions are blocked until level integrity is verified."},
        {"minute": 45, "title": "Handover debt created", "body": "Unresolved level integrity and decision freeze must survive shift handover."},
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
        "mode": plant_a.startup_manager.mode_name,
        "scope": "judge-ready prototype; deterministic trust scoring; not a certified control or safety system",
        "read_only_contract": "ConfidenceOS reads simulator/provider tags and generates trust-aware HMI views; it does not write control commands.",
        "modules": {
            "sensor_simulator": "active",
            "tag_provider": "active",
            "read_only_trust_layer": "active",
            "asset_model": "active",
            "model_graph": "active",
            "hmi_compiler": "active",
            "template_library": "active",
            "generated_runtime": "active",
            "studio": "active",
            "shift_channel": "active",
            "confidence_engine": "active",
            "confidence_explainability": "active",
            "assumption_register": "active",
            "mass_balance_engine": "active",
            "startup_manager": "active",
            "mode_inference": "active",
            "handover_generator": "active",
            "confidence_degradation_forecast": "demo_scope",
            "grounded_operator_explanation": "demo_scope",
            "causal_graph": "active",
            "adaptive_thresholds": "active",
            "advisory_engine": "active",
            "incident_timeline": "active",
            "score_sensitivity": "active",
            "verification_task_workflow": "sqlite_backed",
            "handover_debt": "active",
            "confidence_debt": "active",
            "trust_dependency_graph": "active",
            "compliance_pdf": "active",
            "forensics_replay": "active",
            "sandbox": "active",
            "instrument_integrity_overview": "demo_scope",
        },
        "module_details": {
            "hmi_compiler": "Raw tags -> asset graph -> template binding -> validation -> generated manifest -> publish readiness -> Runtime.",
            "studio_persistence": "Active Studio state is lightweight JSON; import batches and HMI build artifacts are mirrored as immutable SQLite receipts.",
            "confidence_engine": "Governed deterministic trust rubric, not a calibrated probability of correctness.",
            "ai_configuration": "AI explanations are optional; deterministic rules remain authoritative; engineer approval is required before publish.",
            "verification_workflow": "SQLite-backed task lifecycle with immutable audit events; tasks never override confidence.",
            "industrial_integration": "Read-only trust-aware HMI layer beside existing DCS/HMI; OPC UA provider remains a planned read-only boundary.",
        },
    }
