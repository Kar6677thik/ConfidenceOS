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
import hashlib
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
from sqlalchemy.exc import OperationalError

from database import (
    init_db, get_db, SessionLocal,
    SensorReading as SensorReadingModel,
    AnomalyLog as AnomalyLogModel,
    ConfidenceLog as ConfidenceLogModel,
    log_anomaly, get_recent_anomalies,
    log_confidence, log_shift_handover,
    get_confidence_history,
    get_verification_audit,
    prune_timeseries,
)
from plants import PlantManager, UnknownPlantError
from mass_balance import DEFAULT_TOLERANCE
from prediction import predict_all_sensors
from causal_graph import get_graph_state
from adaptive_thresholds import compute_adaptive_envelopes
from advisory import detect_plant_context, build_incidents, build_timeline_events
from assumptions import build_confidence_explanation, confidence_engine_config, load_assumptions
from asset_model import active_asset_model_key, load_asset_model, mass_balance_validation
from model_graph import get_assets, get_model_graph, get_navigation, get_signals
from screen_generator import equipment_manifest
from screen_generator import generate_screen_manifest
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
from demo_service import (
    advance_demo,
    get_demo_state,
    reset_demo,
    start_abnormal_situation,
)
import nlquery


# ─── Global instances ───────────────────────────────────────────────────────

plant_manager = PlantManager()

# Anomaly deduplication: (plant_id:sensor_id:anomaly_type) → last-logged timestamp
_anomaly_cooldown: dict[str, float] = {}
ANOMALY_COOLDOWN_SECONDS = 60.0

BASE_MB_TOLERANCE = DEFAULT_TOLERANCE

# Confidence logging throttle — log every N ticks to avoid DB bloat
_confidence_log_counter: dict[str, int] = {}
CONFIDENCE_LOG_INTERVAL = max(1, int(os.getenv("CONFIDENCEOS_CONFIDENCE_LOG_INTERVAL", "10")))  # log every N ticks
PERSIST_READINGS_INTERVAL = max(1, int(os.getenv("CONFIDENCEOS_PERSIST_READINGS_INTERVAL", "10")))
_plant_loop_status: dict[str, dict] = {}

# Serialize all plant-loop DB writes through one in-process lock so the
# concurrent plant tick loops never commit simultaneously — this removes the
# SQLite writer contention that produced "database is locked" under multi-plant.
_db_write_lock = asyncio.Lock()
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


class SimInjectRequest(BaseModel):
    """Inject one failure into the LIVE simulator source.
    Optional params fall back to sensible per-type training defaults when omitted."""
    plant_id: str = "plant-a"
    sensor_id: str
    failure_type: str
    drift_rate: Optional[float] = None
    stuck_duration: Optional[float] = None
    sg_actual: Optional[float] = None
    sg_calibrated: Optional[float] = None
    commanded_value: Optional[float] = None
    actual_value: Optional[float] = None

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
    # Start background tasks for all plants. Stagger their start so the per-tick
    # commits don't align across plants, easing DB write pressure.
    tasks = []
    for offset, (pid, plant) in enumerate(plant_manager.get_all().items()):
        task = asyncio.create_task(_plant_tick_loop(pid, plant, start_delay=offset * 0.3))
        tasks.append(task)
    # Start time-series retention loop (prevents unbounded ConfidenceLog growth)
    tasks.append(asyncio.create_task(_retention_loop()))
    yield
    # Cancel background tasks
    for task in tasks:
        task.cancel()


# Retention: keep this many hours of high-frequency time-series rows (env-tunable).
TIMESERIES_RETENTION_HOURS = float(os.getenv("CONFIDENCEOS_RETENTION_HOURS", "72"))
RETENTION_SWEEP_SECONDS = float(os.getenv("CONFIDENCEOS_RETENTION_SWEEP_SECONDS", "1800"))


async def _retention_loop():
    """Periodically prune old ConfidenceLog/SensorReading rows so SQLite stays bounded."""
    while True:
        try:
            db = next(get_db())
            try:
                deleted = prune_timeseries(db, keep_hours=TIMESERIES_RETENTION_HOURS)
                if any(deleted.values()):
                    print(f"[retention] pruned {deleted} (keep {TIMESERIES_RETENTION_HOURS}h)")
            finally:
                db.close()
        except Exception as exc:  # never let retention kill the app
            print(f"[retention] sweep failed: {exc}")
        await asyncio.sleep(RETENTION_SWEEP_SECONDS)


app = FastAPI(
    title="ConfidenceOS API",
    description=(
        "ConfidenceOS — a read-only HMI honesty layer: it shows operators how much to "
        "trust each reading, uses physics to catch when a sensor is lying, and compiles "
        "that trust behaviour into reusable HMI screens. The HMI that knows what it does not know."
    ),
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


async def _plant_tick_loop(plant_id: str, plant, start_delay: float = 0.0):
    """Background loop that ticks each plant at 1 Hz and caches state."""
    tick_count = 0
    if start_delay:
        await asyncio.sleep(start_delay)

    try:
        while True:
            db = None
            try:
                now = time.time()
                pending_anomalies = []

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
                # Surface the (engineer-owned) residual-check parameters + honest assumptions.
                plant.latest_mb_state["config"] = plant.mass_balance_engine.config_dict()
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
                            pending_anomalies.append((cr.sensor_id, anomaly_type, description, cr.tier))
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
                        pending_anomalies.append(("SYSTEM", f"mass_balance_{flag.severity.lower()}", flag.message, flag.severity))
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
                        pending_anomalies.append((sf.sensor_id, "stale_reading", desc, "WARNING"))
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

                # V2: increment tick before persistence so live telemetry keeps
                # moving even if SQLite skips a write on this pass.
                tick_count += 1

                persistence_status = "not_run"
                persistence_error = None
                # Only one plant loop commits at a time (in-process serialization).
                await _db_write_lock.acquire()
                try:
                    db = SessionLocal()
                    plant.verification_tokens = sync_auto_tasks(
                        db,
                        plant_id=plant_id,
                        incidents=plant.latest_incidents,
                        confidence=confidence_data,
                        plant_context=plant.latest_context,
                        now=now,
                        commit=False,
                    )

                    for sensor_id, anomaly_type, description, severity in pending_anomalies:
                        log_anomaly(
                            db,
                            sensor_id,
                            anomaly_type,
                            description,
                            severity,
                            plant_id=plant_id,
                            commit=False,
                        )

                    if tick_count % PERSIST_READINGS_INTERVAL == 0:
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
                    persistence_status = "ok"
                except OperationalError as exc:
                    if db:
                        db.rollback()
                    persistence_error = str(exc)
                    if "database is locked" in persistence_error.lower():
                        persistence_status = "skipped_locked"
                        print(f"[PlantTick] Persistence skipped for {plant_id}: database is locked")
                    else:
                        persistence_status = "error"
                        print(f"[PlantTick] Persistence error in {plant_id}: {exc}")
                except Exception as exc:
                    if db:
                        db.rollback()
                    persistence_status = "error"
                    persistence_error = str(exc)
                    print(f"[PlantTick] Persistence error in {plant_id}: {exc}")
                finally:
                    if db:
                        db.close()
                        db = None
                    _db_write_lock.release()

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
                _plant_loop_status[plant_id] = {
                    "status": "ok",
                    "last_tick": now,
                    "tick_count": plant.tag_provider.tick_count,
                    "last_error": None,
                    "persistence_status": persistence_status,
                    "persistence_error": persistence_error,
                }
            except Exception as e:
                if db:
                    db.rollback()
                print(f"[PlantTick] Error in {plant_id}: {e}")
                _plant_loop_status[plant_id] = {
                    "status": "error",
                    "last_tick": time.time(),
                    "tick_count": getattr(plant.tag_provider, "tick_count", 0),
                    "last_error": str(e),
                }
            finally:
                if db:
                    db.close()
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        if db:
            db.close()
    except Exception as e:
        print(f"[PlantTick] Fatal error in {plant_id}: {e}")
        _plant_loop_status[plant_id] = {
            "status": "fatal",
            "last_tick": time.time(),
            "tick_count": getattr(plant.tag_provider, "tick_count", 0),
            "last_error": str(e),
        }
        if db:
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
    # Physics is the alarm: the validated level tag is quarantined when its
    # trust is below HIGH *and* a mass-balance contradiction is active. A frozen
    # level transmitter scores MEDIUM (stability collapses but range/cross-checks
    # can lag), yet the flow-implied inventory proves it is lying — so a MEDIUM
    # tier plus an active physical contradiction is sufficient to quarantine.
    level_quarantined = bool(
        validated_confidence
        and validated_confidence.get("tier") in ("MEDIUM", "LOW", "CRITICAL")
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
            trust_state = "NO_LIVE_SAMPLE"
            trust_reason = "No current reading is available for this tag."
            decision_basis_allowed = False
        elif sensor_id == validated_tag and level_quarantined:
            trust_state = "QUARANTINED"
            trust_reason = "Level trust is degraded while the flow-implied inventory contradicts it (physics is the alarm)."
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


PUMP_STATION_DEMO_ALIASES = {
    "LIT-100": {"source": "LT-5100", "unit": "%", "sensor_type": "level", "scale": 0.5, "offset": 0.0},
    "FIT-101": {"source": "FI-2010", "unit": "m3/h", "sensor_type": "flow_in", "scale": 0.227, "offset": 0.0},
    "FIT-102": {"source": "FO-2020", "unit": "m3/h", "sensor_type": "flow_out", "scale": 0.227, "offset": 0.0},
    "VIB-101": {"source": "ZT-6100", "unit": "mm/s", "sensor_type": "vibration", "scale": 0.08, "offset": 1.2},
}


def _apply_demo_asset_model_bindings(live_state: dict) -> dict:
    """Bind the pump-station metadata model to deterministic demo live values.

    This is not a control integration and not a second simulator. It is a
    transparent demo binding so the same generated Runtime can show live values
    for a second asset model while the read-only simulator still emits the
    original Texas City tag stream.
    """
    if active_asset_model_key() != "pump_station":
        live_state["live_binding_status"] = "native_live_tags"
        live_state.setdefault("demo_alias_bindings", [])
        live_state.setdefault("unbound_tags", [])
        return live_state

    readings = list(live_state.get("readings") or [])
    confidence = list(live_state.get("confidence") or [])
    reading_by_id = {row.get("sensor_id"): row for row in readings if row.get("sensor_id")}
    confidence_by_id = {row.get("sensor_id"): row for row in confidence if row.get("sensor_id")}
    model_tags = {signal.get("tag") for signal in get_signals() if signal.get("tag")}
    live_tags = set(reading_by_id)
    alias_receipts = []

    if model_tags & live_tags:
        live_state["live_binding_status"] = "native_live_tags"
        live_state["demo_alias_bindings"] = []
        live_state["unbound_tags"] = sorted(model_tags - live_tags)
        return live_state

    for target, spec in PUMP_STATION_DEMO_ALIASES.items():
        source = spec["source"]
        source_reading = reading_by_id.get(source)
        if not source_reading:
            continue
        raw_value = source_reading.get("value")
        try:
            value = round(float(raw_value) * float(spec.get("scale", 1.0)) + float(spec.get("offset", 0.0)), 2)
        except (TypeError, ValueError):
            value = raw_value
        readings.append({
            **source_reading,
            "sensor_id": target,
            "tag": target,
            "value": value,
            "unit": spec["unit"],
            "sensor_type": spec["sensor_type"],
            "demo_bound_from": source,
            "read_only_demo_binding": True,
        })
        source_confidence = confidence_by_id.get(source)
        if source_confidence:
            confidence.append({
                **source_confidence,
                "sensor_id": target,
                "tag": target,
                "sensor_type": spec["sensor_type"],
                "trust_reason": (
                    f"Read-only demo binding from {source}; use for pump-station generated HMI demonstration only."
                ),
                "demo_bound_from": source,
                "read_only_demo_binding": True,
            })
        alias_receipts.append({
            "target_tag": target,
            "source_tag": source,
            "read_only": True,
            "purpose": "demo live binding for alternate asset model",
        })

    live_state["readings"] = readings
    live_state["confidence"] = confidence
    live_state["demo_alias_bindings"] = alias_receipts
    live_state["live_binding_status"] = "demo_alias_live_tags" if alias_receipts else "metadata_only_no_live_tags"
    live_state["unbound_tags"] = sorted(model_tags - {row.get("sensor_id") for row in readings if row.get("sensor_id")})
    return live_state


def _runtime_live_state(plant_id: str, plant) -> dict:
    """Collect frontend-friendly live state for generated Runtime manifests."""
    confidence = list(plant.latest_confidence.values())
    if confidence and any("trust_state" not in item for item in confidence):
        confidence = _derive_trust_states(confidence, plant.latest_readings, plant.latest_mb_state)
    now = time.time()
    verification_tasks = [normalize_verification_task(task, now) for task in plant.verification_tokens or []]
    active_tasks = active_verification_tokens(plant.verification_tokens, now)
    live_state = {
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
        "demo_state": get_demo_state(plant_id, plant, _plant_loop_status.get(plant_id, {})),
    }
    return _apply_demo_asset_model_bindings(live_state)


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
                "demo_state": get_demo_state(plant_id, plant, _plant_loop_status.get(plant_id, {})),
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
    live_state = _runtime_live_state(plant_id, plant)
    try:
        manifest = studio_runtime_manifest(
            role=role,
            context=context,
            live_state=live_state,
        )
        return _annotate_generated_preview(manifest, live_state)
    except Exception as exc:
        assignments = studio_overview().get("state", {}).get("assignments", [])
        manifest = generate_screen_manifest(
            role=role,
            context=context,
            live_state=live_state,
            assignments=assignments,
            build_context={
                "build_id": "runtime-fallback",
                "validation_status": "PASS_WITH_WARNINGS",
                "validation": {
                    "info": [{
                        "rule": "runtime_fallback_generation",
                        "message": "Generated fallback Runtime because published manifest hydration failed.",
                    }],
                    "warnings": [{
                        "rule": "runtime_manifest_hydration_failed",
                        "message": str(exc),
                    }],
                    "blocking": [],
                },
                "receipts": [{
                    "severity": "WARNING",
                    "message": "Runtime fallback generated from asset model and template assignments.",
                    "source": "api/screens/generated",
                }],
            },
        )
        return _annotate_generated_preview({
            **manifest,
            "runtime_source": "fallback_runtime_generation",
            "runtime_warning": str(exc),
        }, live_state)


def _annotate_generated_preview(manifest: dict, live_state: dict) -> dict:
    """Flag the Runtime as a metadata-only preview when the active asset model's
    signals have no matching live tags in the stream (e.g. a non-Texas-City model
    is active while the live simulator still streams the demo tags). Engineer/
    Manager see this honesty notice; Operator gating is handled in the frontend.
    """
    manifest["live_binding_status"] = live_state.get("live_binding_status", "unknown")
    manifest["demo_alias_bindings"] = live_state.get("demo_alias_bindings", [])
    manifest["unbound_tags"] = live_state.get("unbound_tags", [])
    manifest["demo_state"] = live_state.get("demo_state", {})
    if live_state.get("live_binding_status") == "demo_alias_live_tags":
        manifest["runtime_preview"] = False
        manifest["runtime_notice"] = (
            "Live demo binding active: pump-station tags are read-only aliases "
            "from the simulator stream. No control commands or setpoints are written."
        )
        return manifest
    try:
        model_tags = {s.get("tag") for s in get_signals() if s.get("tag")}
        live_tags = {r.get("sensor_id") for r in (live_state.get("readings") or []) if r.get("sensor_id")}
    except Exception:
        return manifest
    if model_tags and live_tags and not (model_tags & live_tags):
        manifest["runtime_preview"] = True
        manifest["runtime_notice"] = (
            "Generated from metadata - preview only (no live tags bound). "
            "The active asset model's signals are not present in this plant's live stream."
        )
    else:
        manifest.setdefault("runtime_preview", False)
    return manifest


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


# ─── Simulator training controls ─────────────────────────────────────────────
# These endpoints manipulate the SIMULATOR source so engineering/training users
# can trigger sensor failures live. They do NOT write any plant
# control command (the read-only-to-plant contract is unchanged; tag_provider
# .write_tag still raises). They are scoped to the simulator-backed provider.

@app.get("/api/simulation/state")
def get_simulation_state(plant_id: str = Query(default="plant-a")):
    """Return simulator scenario phase and source facts."""
    plant = plant_manager.get(plant_id)
    return get_demo_state(plant_id, plant, _plant_loop_status.get(plant_id, {}))


@app.post("/api/simulation/reset-source")
def reset_simulation_source(plant_id: str = Query(default="plant-a")):
    """Reset only the simulator source and scenario state.

    This does not reset Studio compiler state or shift-channel notes.
    """
    plant = _require_simulator_plant(plant_id)
    state = reset_demo(plant_id, plant)
    return {"status": "reset", "simulation_state": state, "demo_state": state}


@app.post("/api/simulation/start-abnormal-situation")
def start_simulation_abnormal_situation(plant_id: str = Query(default="plant-a")):
    """Start the abnormal simulator scenario without changing Studio state."""
    plant = _require_simulator_plant(plant_id)
    state = start_abnormal_situation(plant_id, plant)
    return {"status": "started", "simulation_state": state, "demo_state": state}


@app.post("/api/simulation/advance")
def advance_simulation_scenario(plant_id: str = Query(default="plant-a")):
    """Advance the simulator scenario phase without writing plant controls."""
    plant = _require_simulator_plant(plant_id)
    state = advance_demo(plant_id, plant)
    return {"status": "advanced", "simulation_state": state, "demo_state": state}


@app.get("/api/demo/state")
def get_judge_demo_state(plant_id: str = Query(default="plant-a")):
    """Compatibility alias for simulator scenario state."""
    plant = plant_manager.get(plant_id)
    return get_demo_state(plant_id, plant, _plant_loop_status.get(plant_id, {}))


@app.post("/api/demo/reset")
def reset_judge_demo(plant_id: str = Query(default="plant-a")):
    """Compatibility endpoint: reset the app-wide training baseline.

    This resets ConfidenceOS training state: the read-only simulator, shift
    notes, Studio compiler state, and active asset model. It does not write any
    controller command, setpoint, mode, or alarm acknowledgement.
    """
    plant = _require_simulator_plant(plant_id)
    studio_state = studio_reset()
    reset_shift_notes()
    state = reset_demo(plant_id, plant)
    return {
        "status": "reset",
        "demo_state": state,
        "studio_state": {
            "selected_asset_model": studio_state.get("selected_asset_model"),
            "published_build_id": studio_state.get("published_build_id"),
            "build_counter": studio_state.get("build_counter"),
            "read_only_boundary": "Studio reset changes only ConfidenceOS compiler files and simulator-backed demo state.",
        },
    }


@app.post("/api/demo/start-abnormal-situation")
def start_judge_abnormal_situation(plant_id: str = Query(default="plant-a")):
    """Compatibility endpoint: trigger the trust-quarantine simulator scenario."""
    plant = _require_simulator_plant(plant_id)
    # The primary judge story is the Texas City vessel. Keep the active compiler
    # model aligned so Runtime language, action contracts, and trust graph do not
    # inherit a previous Pump Station exploration.
    if active_asset_model_key() != "texas_city_vessel":
        studio_select_asset_model("texas_city_vessel")
    state = start_abnormal_situation(plant_id, plant)
    return {"status": "started", "demo_state": state}


@app.post("/api/demo/advance")
def advance_judge_demo(plant_id: str = Query(default="plant-a")):
    """Compatibility endpoint: advance the simulator scenario phase without writing plant controls."""
    plant = _require_simulator_plant(plant_id)
    state = advance_demo(plant_id, plant)
    return {"status": "advanced", "demo_state": state}


_VALID_FAILURE_TYPES = {
    "calibration_drift", "stuck_reading", "sg_mismatch", "command_state_decoupling",
}


def _require_simulator_plant(plant_id: str):
    """Return the plant if it is simulator-backed; else 400."""
    from tag_provider import SimulatorProvider
    plant = plant_manager.get(plant_id)
    if not isinstance(plant.tag_provider, SimulatorProvider) or getattr(plant, "simulator", None) is None:
        raise HTTPException(
            status_code=400,
            detail="Live failure injection is only supported on the simulator provider.",
        )
    return plant


@app.post("/api/sim/inject")
def sim_inject(request: SimInjectRequest):
    """Inject a single failure into the LIVE simulator so the trust
    pipeline reacts immediately. Configures the simulated source, not a plant
    control write."""
    from simulator import FailureConfig
    plant = _require_simulator_plant(request.plant_id)
    if request.failure_type not in _VALID_FAILURE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"failure_type must be one of {sorted(_VALID_FAILURE_TYPES)}",
        )
    if request.sensor_id not in plant.simulator.sensors:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown sensor '{request.sensor_id}'. Known: {sorted(plant.simulator.sensors)}",
        )
    # Fire immediately: start_time = current elapsed seconds.
    start = plant.simulator.elapsed()
    failure = FailureConfig(
        sensor_id=request.sensor_id,
        failure_type=request.failure_type,
        start_time=start,
        drift_rate=request.drift_rate if request.drift_rate is not None else 0.5,
        stuck_duration=request.stuck_duration if request.stuck_duration is not None else 0.0,
        sg_actual=request.sg_actual if request.sg_actual is not None else 0.65,
        sg_calibrated=request.sg_calibrated if request.sg_calibrated is not None else 0.80,
        commanded_value=request.commanded_value if request.commanded_value is not None else 0.0,
        actual_value=request.actual_value if request.actual_value is not None else 85.0,
    )
    plant.simulator.failures.append(failure)
    return {
        "status": "injected",
        "simulation_source_only": True,
        "failure": {
            "sensor_id": failure.sensor_id,
            "failure_type": failure.failure_type,
            "start_time": round(start, 1),
        },
        "active_failures": len(plant.simulator.failures),
    }


@app.post("/api/sim/clear")
def sim_clear(plant_id: str = Query(default="plant-a")):
    """Clear all injected failures from the LIVE simulator and reset
    it to normal operation. Does not write any plant control."""
    plant = _require_simulator_plant(plant_id)
    plant.simulator.failures.clear()
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    state = reset_demo(plant_id, plant)
    return {"status": "cleared", "simulation_source_only": True, "active_failures": 0, "simulation_state": state}


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

    return {
        "hours": hours,
        "bucket_minutes": bucket_minutes,
        "sample_count": len(rows),
        "source": "confidence_logs",
        "status": "active" if trend else "insufficient_history",
        "trend": trend,
    }


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
                "name": "Texas City Incident Replay",
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
    """Build a compact deterministic Texas City training replay."""
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
        "name": "Texas City Incident Replay",
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

    # Section 5: Field verification task state. This is operational evidence,
    # not a control action and not a confidence override.
    verification_tasks = list_verification_tasks(
        db,
        plant_id=request.plant_id,
        include_closed=True,
        expire=True,
        limit=50,
    )
    verification_task_rows = [
        {
            "task_id": task.get("task_id"),
            "sensor_id": task.get("sensor_id"),
            "state": task.get("state"),
            "assigned_role": task.get("assigned_role"),
            "verification_method": task.get("verification_method"),
            "created_at": task.get("created_at_iso"),
            "valid_until": task.get("valid_until_iso"),
            "handover_required": task.get("handover_required"),
            "confidence_override": False,
            "note": task.get("note") or task.get("last_evidence_summary"),
        }
        for task in verification_tasks
    ]
    active_verification_count = sum(1 for task in verification_tasks if task.get("active"))
    handover_required_task_count = sum(1 for task in verification_tasks if task.get("handover_required"))

    # Section 6: Recommendations (deterministic from available evidence)
    recommendations = _generate_compliance_recommendations(
        alarm_by_severity, sensor_reliability, mb_anomalies, plant
    )

    all_sections = {
        "data_coverage": {
            "source": "ConfidenceOS simulator/runtime logs",
            "window_hours": request.hours,
            "anomaly_rows": alarm_count,
            "confidence_rows_by_sensor": {
                sid: payload.get("data_points", 0)
                for sid, payload in sensor_reliability.items()
            },
            "handover_rows": len(handovers),
            "mass_balance_rows": len(mb_anomalies),
            "verification_task_rows": len(verification_task_rows),
            "production_certification": False,
            "operator_note": "Empty counts mean the source log had no rows for that category in the selected window.",
        },
        "runtime_state_at_generation": {
            "context_status": plant.latest_context.get("status") or plant.latest_context.get("state") or "UNKNOWN",
            "context_focus": plant.latest_context.get("operator_focus") or plant.latest_context.get("recommended_focus"),
            "active_incident_count": len(plant.latest_incidents or []),
            "active_verification_tasks": active_verification_count,
            "handover_acceptance": (plant.latest_handover_debt or {}).get("handover_acceptance") or "not_evaluated",
            "latest_tick_available": bool(plant.latest_readings),
            "read_only_boundary": "ConfidenceOS does not write setpoints, controller modes, tag values, or alarm acknowledgements.",
        },
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
        "field_verification_tasks": {
            "count": len(verification_task_rows),
            "active_count": active_verification_count,
            "handover_required_count": handover_required_task_count,
            "confidence_override": False,
            "entries": verification_task_rows,
        },
        "recommendations": recommendations,
    }
    section_profiles = {
        "alarm": ["data_coverage", "runtime_state_at_generation", "alarm_summary", "mass_balance_summary", "recommendations"],
        "sensor": ["data_coverage", "runtime_state_at_generation", "sensor_reliability", "field_verification_tasks", "recommendations"],
        "handover": ["data_coverage", "runtime_state_at_generation", "shift_handover_log", "field_verification_tasks", "recommendations"],
        "full": list(all_sections.keys()),
    }
    selected_section_keys = section_profiles.get(request.report_type, section_profiles["full"])

    report = {
        "plant_id": request.plant_id,
        "plant_name": plant.name,
        "title": "Operational Summary Report",
        "report_type": request.report_type,
        "period_hours": request.hours,
        "generated_at": datetime.utcnow().isoformat(),
        "sections": {key: all_sections[key] for key in selected_section_keys},
        "available_sections": list(all_sections.keys()),
        "included_sections": selected_section_keys,
        "limitations": [
            "Generated from ConfidenceOS logged simulator/runtime data only.",
            "Confidence values are governed trust scores, not calibrated probabilities.",
            "This report does not certify regulatory compliance or replace DCS/HMI records.",
            "False-positive, silence-rate, and digital-signature claims are not made unless source data exists.",
        ],
    }
    # Honest provenance: a SHA-256 content hash + generator identity. This is NOT a
    # cryptographic signature — it lets a reader verify the report wasn't altered, without
    # claiming a trusted authority signed it. (UI must not say "Digitally Signed".)
    canonical = json.dumps(report, sort_keys=True, default=str).encode("utf-8")
    report["provenance"] = {
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "generator": "ConfidenceOS Advisory Engine",
        "signed": False,
        "note": "Unsigned operational summary. Content hash allows tamper-evidence, not authority of signature.",
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
                "action": f"Calibrate {sid} immediately - {age:.0f} days since last calibration.",
            })
        elif age > 40:
            recs.append({
                "priority": "high",
                "action": f"Schedule calibration for {sid} within 1 week - {age:.0f} days elapsed.",
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
        recs.append({
            "priority": "info",
            "action": "No critical issues identified from available ConfidenceOS logs in this reporting window. This is not a production compliance certification.",
        })

    return recs


# ─── Simulation Sandbox (Module 15) ──────────────────────────────────────────

def _format_compliance_report_text(report: dict) -> str:
    sections = report.get("sections", {})
    alarm = sections.get("alarm_summary", {})
    mb = sections.get("mass_balance_summary", {})
    handover = sections.get("shift_handover_log", {})
    reliability = sections.get("sensor_reliability", {})
    coverage = sections.get("data_coverage", {})
    runtime_state = sections.get("runtime_state_at_generation", {})
    verification = sections.get("field_verification_tasks", {})
    recommendations = sections.get("recommendations", [])
    severity_items = alarm.get("by_severity", {}) or {}
    top_sensors = alarm.get("top_10_sensors", []) or []
    flags = mb.get("flags", []) or []
    handover_entries = handover.get("entries", []) or []

    lines = [
        "ConfidenceOS Operational Summary Report",
        f"Plant: {report.get('plant_name')} ({report.get('plant_id')})",
        f"Report type: {report.get('report_type')}",
        f"Period: {report.get('period_hours')} hours",
        f"Generated: {report.get('generated_at')}",
        "",
        "Scope And Limitations",
    ]
    lines.extend([f"- {item}" for item in report.get("limitations", [])])
    lines.extend([
        "",
        "Data Coverage",
        f"Source: {coverage.get('source', 'ConfidenceOS runtime logs')}",
        f"Anomaly rows: {coverage.get('anomaly_rows', 0)}",
        f"Mass-balance rows: {coverage.get('mass_balance_rows', 0)}",
        f"Handover rows: {coverage.get('handover_rows', 0)}",
        f"Production certification: {coverage.get('production_certification', False)}",
        f"Note: {coverage.get('operator_note', 'Empty counts mean no source rows were logged in the selected window.')}",
        "",
        "Runtime State At Generation",
        f"Context status: {runtime_state.get('context_status', 'not included')}",
        f"Operator focus: {runtime_state.get('context_focus', 'not included')}",
        f"Active incidents: {runtime_state.get('active_incident_count', 'not included')}",
        f"Active verification tasks: {runtime_state.get('active_verification_tasks', 'not included')}",
        f"Handover acceptance: {runtime_state.get('handover_acceptance', 'not included')}",
        f"Latest tick available: {runtime_state.get('latest_tick_available', 'not included')}",
        f"Read-only boundary: {runtime_state.get('read_only_boundary', 'not included')}",
    ])
    lines.extend([
        "",
        "Alarm Summary",
        f"Total alarms: {alarm.get('total_alarms', 0)}",
        f"Alarm rate/hour: {alarm.get('alarm_rate_per_hour', 0)}",
        "By severity:",
    ])
    if severity_items:
        for severity, count in sorted(severity_items.items()):
            lines.append(f"- {severity}: {count}")
    else:
        lines.append("- No anomaly rows were available in this reporting window.")
    lines.append("Top contributing sensors:")
    if top_sensors:
        for item in top_sensors:
            lines.append(f"- {item.get('sensor_id', 'UNKNOWN')}: {item.get('count', 0)} events")
    else:
        lines.append("- No sensor alarm concentration detected.")
    lines.extend([
        "",
        "Sensor Trust Summary",
    ])
    if reliability:
        for sid, rel in sorted(reliability.items()):
            tier_dist = rel.get("tier_distribution", {}) or {}
            dist = ", ".join(f"{key} {value}%" for key, value in tier_dist.items())
            lines.append(
                f"- {sid}: current {rel.get('current_confidence', 'n/a')}%, "
                f"calibration age {rel.get('calibration_age', 'n/a')} days, "
                f"{rel.get('data_points', 0)} samples ({dist})"
            )
    else:
        lines.append("- No confidence history rows were available in this reporting window.")
    lines.extend([
        "",
        "Mass-Balance Summary",
        f"Total flags: {mb.get('total_flags', 0)}",
        "Flag details:",
    ])
    if flags:
        for flag in flags[:20]:
            lines.append(
                f"- {flag.get('timestamp', flag.get('created_at', 'n/a'))}: "
                f"{flag.get('severity', 'INFO')} / {flag.get('sensor_id', 'UNKNOWN')} / "
                f"{flag.get('anomaly_type', 'mass_balance')} / {flag.get('description', flag.get('message', 'no description'))}"
            )
    else:
        lines.append("- No mass-balance flags logged in this period.")
    lines.extend([
        "",
        "Shift Handover Log",
        f"Generated handovers: {handover.get('count', 0)}",
        "Entries:",
    ])
    if handover_entries:
        for entry in handover_entries[:12]:
            lines.append(
                f"- {entry.get('generated_at', 'n/a')} / {entry.get('source', 'unknown')}: "
                f"{entry.get('brief_text', '').replace(chr(10), ' ')[:220]}"
            )
    else:
        lines.append("- No handover entries logged in this period.")
    lines.extend([
        "",
        "Field Verification Tasks",
        f"Total tasks: {verification.get('count', 0)}",
        f"Active tasks: {verification.get('active_count', 0)}",
        f"Handover-required tasks: {verification.get('handover_required_count', 0)}",
        f"Confidence override: {verification.get('confidence_override', False)}",
        "Entries:",
    ])
    verification_entries = verification.get("entries", []) or []
    if verification_entries:
        for task in verification_entries[:20]:
            lines.append(
                f"- {task.get('sensor_id', 'UNKNOWN')} / {task.get('state', 'UNKNOWN')} / "
                f"{task.get('assigned_role', 'Maintenance')} / due {task.get('valid_until', 'n/a')} / "
                f"handover_required={task.get('handover_required', False)}"
            )
    else:
        lines.append("- No field verification tasks logged for this report profile/window.")
    lines.extend([
        "",
        "Recommendations",
    ])
    for rec in recommendations:
        lines.append(f"- {rec.get('priority', 'info').upper()}: {rec.get('action', '')}")
    provenance = report.get("provenance", {})
    lines.extend([
        "",
        "Provenance (unsigned)",
        f"Content SHA-256: {provenance.get('content_sha256', 'n/a')}",
        f"Generator: {provenance.get('generator', 'ConfidenceOS Advisory Engine')}",
        "Note: tamper-evident content hash, not a cryptographic signature.",
    ])
    return "\n".join(lines)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(text: str) -> bytes:
    """Create a small multi-page PDF containing plain report text."""
    wrapped_lines = []
    for line in text.splitlines():
        if not line:
            wrapped_lines.append("")
            continue
        while len(line) > 95:
            wrapped_lines.append(line[:95])
            line = "  " + line[95:]
        wrapped_lines.append(line)

    pages = [wrapped_lines[i:i + 48] for i in range(0, len(wrapped_lines), 48)] or [[]]
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids ["
        + b" ".join(f"{3 + i * 2} 0 R".encode("ascii") for i in range(len(pages)))
        + b"] /Count "
        + str(len(pages)).encode("ascii")
        + b" >> endobj\n",
    ]
    for index, page_lines in enumerate(pages):
        page_obj = 3 + index * 2
        content_obj = page_obj + 1
        content_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for line in page_lines:
            content_lines.append(f"({_pdf_escape(line)}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", "replace")
        objects.append(
            f"{page_obj} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> /Contents {content_obj} 0 R >> endobj\n".encode("ascii")
        )
        objects.append(
            f"{content_obj} 0 obj << /Length {len(stream)} >> stream\n".encode("ascii")
            + stream
            + b"\nendstream endobj\n"
        )
    font_obj = 3 + len(pages) * 2
    objects.append(f"{font_obj} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n".encode("ascii"))
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
    from simulator import SensorSimulator, DEFAULT_SENSORS
    from confidence import ConfidenceEngine
    from mass_balance import MassBalanceEngine

    # Create isolated instances
    sensors = list(DEFAULT_SENSORS)
    if request.sensor_id not in {sensor.sensor_id for sensor in sensors}:
        sensors.append(_sandbox_sensor_config(request.sensor_id))
    sim = SensorSimulator(sensors=sensors)
    confidence_cfg = confidence_engine_config()
    ce = ConfidenceEngine(
        weights=confidence_cfg["weights"],
        calibration_interval_days=confidence_cfg["calibration_interval_days"],
    )
    ce.set_adaptive_envelopes(confidence_cfg["operating_envelopes"])
    mbe = MassBalanceEngine()

    # Copy calibration ages from the target plant
    plant = plant_manager.get(request.plant_id)
    for sid, age in plant.config["calibration_ages"].items():
        ce.set_calibration_age(sid, age)

    severity_factor = {"mild": 0.6, "moderate": 1.0, "severe": 1.8}.get(request.severity, 1.0)

    # Simulate the failure progression
    results = []
    duration_ticks = int(request.duration_hours * 3600 / 60)  # Sample every 60 seconds
    virtual_start = time.time()
    for i in range(min(duration_ticks, 360)):  # Cap at 360 samples
        time_hours = i * 60 / 3600
        readings = sim.tick()
        virtual_timestamp = virtual_start + (i * 60)
        for reading in readings:
            reading["timestamp"] = virtual_timestamp
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
            mb_applicable = selected_reading.get("sensor_type") in {"level", "flow_in", "flow_out", "valve"}
            mb_payload = mb_state.to_dict() if mb_applicable else {
                "applicable": False,
                "reason": "Selected signal is not part of the inventory mass-balance validation relationship.",
                "discrepancy": None,
                "flags": [],
            }
            _apply_sandbox_confidence_degradation(
                selected_confidence,
                request.failure_mode,
                request.severity,
                time_hours,
            )
            results.append({
                "time_hours": round(time_hours, 2),
                "reading": selected_reading,
                "confidence": selected_confidence,
                "confidence_pct": selected_confidence["confidence_pct"],
                "tier": selected_confidence["tier"],
                "reasons": selected_confidence["reasons"][:2],
                "mass_balance": mb_payload,
                "flags": [f.to_dict() for f in mb_state.flags] if mb_applicable else [],
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
        "sample_interval_seconds": 60,
        "source": "isolated_sandbox_virtual_time",
        "note": "Sandbox uses virtual timestamps and does not affect live Runtime tags.",
        "results": results,
    }


def _sandbox_sensor_config(sensor_id: str):
    """Create a lightweight simulator config for a metadata-only/model tag."""
    from simulator import SensorConfig

    normalized = sensor_id.upper().replace("_", "-")
    if normalized.startswith(("LT", "LIT")):
        return SensorConfig(sensor_id, "level", "ft", 50.0, 0.3, 0.0, 200.0, 5.0, 600.0)
    if normalized.startswith(("FI", "FIT")):
        return SensorConfig(sensor_id, "flow_in", "gpm", 132.0, 2.0, 0.0, 500.0, 10.0, 480.0)
    if normalized.startswith(("FO", "FOT")):
        return SensorConfig(sensor_id, "flow_out", "gpm", 118.0, 2.0, 0.0, 500.0, 8.0, 520.0)
    if normalized.startswith("PT"):
        return SensorConfig(sensor_id, "pressure", "psi", 21.0, 0.2, 0.0, 100.0, 1.5, 700.0)
    if normalized.startswith(("TT", "TEMP")):
        return SensorConfig(sensor_id, "temperature", "F", 350.0, 1.0, 60.0, 800.0, 8.0, 900.0)
    if normalized.startswith(("ZT", "XV")):
        return SensorConfig(sensor_id, "valve", "%", 60.0, 0.1, 0.0, 100.0, 0.0, 1.0)
    if normalized.startswith("VIB"):
        return SensorConfig(sensor_id, "vibration", "mm/s", 2.4, 0.12, 0.0, 25.0, 0.4, 360.0)
    return SensorConfig(sensor_id, "generic", "eu", 50.0, 0.5, 0.0, 100.0, 2.0, 600.0)


def _apply_sandbox_confidence_degradation(confidence: dict, failure_mode: str, severity: str, time_hours: float) -> None:
    """Make sandbox trust trajectories visible without touching live confidence state."""
    factor = {"mild": 0.7, "moderate": 1.0, "severe": 1.45}.get(severity, 1.0)
    mode_factor = {
        "calibration_drift": ("calibration", 6.0),
        "stuck_reading": ("stability", 7.5),
        "sg_mismatch": ("physical_plausibility", 8.0),
        "command_state_decoupling": ("cross_sensor", 7.0),
    }.get(failure_mode, ("stability", 4.0))
    factor_name, rate = mode_factor
    penalty = min(75.0, time_hours * rate * factor)
    baseline = float(confidence.get("confidence_pct", 100.0))
    adjusted = max(0.0, baseline - penalty)
    confidence["confidence_pct"] = round(adjusted, 1)
    confidence["tier"] = "HIGH" if adjusted >= 80 else "MEDIUM" if adjusted >= 50 else "LOW" if adjusted >= 20 else "CRITICAL"
    sub_scores = dict(confidence.get("sub_scores") or {})
    current_score = float(sub_scores.get(factor_name, 1.0))
    sub_scores[factor_name] = round(max(0.0, min(1.0, current_score - penalty / 100.0)), 3)
    confidence["sub_scores"] = sub_scores
    confidence["dominant_factor"] = factor_name
    confidence["recommended_action"] = "Sandbox-only confidence degradation: verify the affected evidence path before using this signal as an operating basis."


# ─── Health check ────────────────────────────────────────────────────────────

def _readiness_component(status: str, message: str, **details) -> dict:
    return {
        "status": status,
        "message": message,
        **{key: value for key, value in details.items() if value is not None},
    }


def _count_template_entries(catalog: dict, key: str) -> int:
    value = catalog.get(key)
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list):
        return len(value)
    return 0


def _runtime_readiness_report(plant_id: str, plant, stream_health: str, persistence_health: str) -> dict:
    """Return operator-facing readiness without making Docker health brittle."""
    components: dict[str, dict] = {}
    issues: list[dict] = []

    components["stream"] = _readiness_component(
        stream_health,
        "Live simulator/provider stream is ticking." if stream_health == "ok" else "Live stream is warming up or delayed.",
        recent_plant_loops=sum(1 for status in _plant_loop_status.values() if status.get("status") == "ok"),
    )
    if stream_health != "ok":
        issues.append({"severity": "WARNING", "component": "stream", "message": components["stream"]["message"]})

    components["persistence"] = _readiness_component(
        persistence_health,
        "SQLite audit persistence is accepting writes." if persistence_health == "ok" else "SQLite audit persistence is delayed; live Runtime remains read-only.",
    )
    if persistence_health in {"degraded", "error"}:
        issues.append({"severity": "WARNING", "component": "persistence", "message": components["persistence"]["message"]})

    try:
        model = load_asset_model()
        components["asset_model"] = _readiness_component(
            "ok",
            "Active asset model loaded.",
            model_key=active_asset_model_key(),
            plant=model.get("plant", {}).get("name") or model.get("plant", {}).get("id"),
            signal_count=len(get_signals()),
            asset_count=len(get_assets()),
        )
    except Exception as exc:
        components["asset_model"] = _readiness_component("error", "Asset model could not be loaded.", error=str(exc))
        issues.append({"severity": "BLOCKING", "component": "asset_model", "message": str(exc)})

    try:
        catalog = get_template_catalog()
        components["template_library"] = _readiness_component(
            "ok",
            "Reusable HMI templates loaded.",
            equipment_templates=_count_template_entries(catalog, "equipment_templates"),
            signal_templates=_count_template_entries(catalog, "signal_templates"),
        )
    except Exception as exc:
        components["template_library"] = _readiness_component("error", "Template library could not be loaded.", error=str(exc))
        issues.append({"severity": "BLOCKING", "component": "template_library", "message": str(exc)})

    try:
        build = studio_current_build()
        blocking_count = len(build.get("validation", {}).get("blocking", []) or [])
        components["studio_compiler"] = _readiness_component(
            "ok" if blocking_count == 0 else "blocked",
            "Latest Studio build can publish." if build.get("can_publish") else "Latest Studio build is blocked or not ready to publish.",
            build_id=build.get("build_id"),
            build_status=str(build.get("status") or "NOT_RUN").upper(),
            can_publish=bool(build.get("can_publish")),
            blocking_count=blocking_count,
        )
        if blocking_count:
            issues.append({"severity": "BLOCKING", "component": "studio_compiler", "message": "Compiler has blocking validation issues."})
    except Exception as exc:
        components["studio_compiler"] = _readiness_component("error", "Studio compiler state could not be read.", error=str(exc))
        issues.append({"severity": "BLOCKING", "component": "studio_compiler", "message": str(exc)})

    try:
        live_state = _runtime_live_state(plant_id, plant)
        manifest = studio_runtime_manifest(role="Operator", context="auto", live_state=live_state)
        publish_state = manifest.get("runtime_publish_state") or "UNKNOWN"
        runtime_status = "ok" if publish_state in {"PUBLISHED", "PUBLISHED_WITH_WARNINGS"} else "preview"
        components["generated_runtime"] = _readiness_component(
            runtime_status,
            "Published generated Runtime is available." if runtime_status == "ok" else "Runtime is available as metadata preview until Studio publishes a passing build.",
            build_id=manifest.get("build_id"),
            published_build_id=manifest.get("published_build_id"),
            runtime_publish_state=publish_state,
            runtime_source=manifest.get("runtime_source"),
            faceplate_count=len(manifest.get("faceplates", []) or []),
            situation_count=len(manifest.get("situations", []) or []),
            live_binding_status=live_state.get("live_binding_status"),
        )
        if runtime_status != "ok":
            issues.append({"severity": "WARNING", "component": "generated_runtime", "message": components["generated_runtime"]["message"]})
    except Exception as exc:
        components["generated_runtime"] = _readiness_component("error", "Generated Runtime manifest failed to hydrate.", error=str(exc))
        issues.append({"severity": "BLOCKING", "component": "generated_runtime", "message": str(exc)})

    try:
        channel = build_shift_channel(plant_id, plant)
        components["shift_channel"] = _readiness_component(
            "ok",
            "Shift channel can summarize unresolved operating debt.",
            pinned_count=len(channel.get("pinned", []) or []),
            entry_count=len(channel.get("thread", []) or channel.get("entries", []) or []),
            handover_blocked=bool(channel.get("handover_acceptance_blocked")),
        )
    except Exception as exc:
        components["shift_channel"] = _readiness_component("error", "Shift channel failed to build.", error=str(exc))
        issues.append({"severity": "WARNING", "component": "shift_channel", "message": str(exc)})

    if any(issue.get("severity") == "BLOCKING" for issue in issues):
        summary = "blocked"
    elif issues:
        summary = "degraded"
    else:
        summary = "ready"

    return {
        "summary": summary,
        "components": components,
        "issues": issues,
        "operator_runtime_ready": components.get("generated_runtime", {}).get("status") == "ok",
        "read_only_boundary": "ConfidenceOS reads plant/simulator tags and generated metadata only; it does not write controls, modes, setpoints, or alarm acknowledgements.",
    }


@app.get("/api/health")
def health_check():
    """Basic health check."""
    plant_a = plant_manager.get("plant-a")

    # Stream health: are the plant tick loops alive and ticking recently?
    statuses = list(_plant_loop_status.values())
    now_ts = time.time()
    loops_ok = [s for s in statuses if s.get("status") == "ok"]
    recently_ticked = any((now_ts - s.get("last_tick", 0)) < 5.0 for s in loops_ok)
    if not statuses:
        stream_health = "warming_up"
    elif recently_ticked:
        stream_health = "ok"
    else:
        stream_health = "degraded"

    # Persistence health is independent of stream health: the live stream can be
    # perfectly healthy while DB writes are being skipped under lock contention.
    persistence_states = [s.get("persistence_status") for s in statuses]
    if any(ps == "error" for ps in persistence_states):
        persistence_health = "error"
    elif any(ps == "skipped_locked" for ps in persistence_states):
        persistence_health = "degraded"  # history delayed, live unaffected
    elif any(ps == "ok" for ps in persistence_states):
        persistence_health = "ok"
    else:
        persistence_health = "warming_up"
    readiness = _runtime_readiness_report("plant-a", plant_a, stream_health, persistence_health)

    return {
        "status": "ok",
        "version": "2.0.0",
        "product": (
            "ConfidenceOS is a read-only HMI honesty layer. It reads existing plant tags "
            "without writing controls, scores how much to trust every reading, and uses "
            "physics (mass balance) to catch when a sensor is lying. Studio compiles that "
            "trust behaviour into reusable HMI screens so it scales across plants."
        ),
        "uptime_seconds": round(plant_a.tag_provider.elapsed(), 1),
        "tick_count": plant_a.tag_provider.tick_count,
        "active_connections": len(active_connections),
        "plants": len(plant_manager.plants),
        "plant_loops": _plant_loop_status,
        # Explicit, separable health: live stream vs durable persistence. "Live
        # stream offline" and "history delayed" are different operational states.
        "stream_health": stream_health,
        "persistence_health": persistence_health,
        "db_status": "writing" if any(s.get("status") == "ok" for s in _plant_loop_status.values()) else "warming_up",
        "readiness": readiness,
        "readiness_summary": readiness.get("summary"),
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
