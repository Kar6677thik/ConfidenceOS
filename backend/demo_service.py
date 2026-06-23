"""
demo_service.py - simulator scenario orchestration for ConfidenceOS.

This module only manipulates the software simulator and in-memory scenario labels.
It never writes to a plant, controller, setpoint, alarm acknowledgement, or DCS.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from simulator import FailureConfig


_DEMO_STATE: dict[str, dict] = {}


PHASES = [
    "NORMAL_BASELINE",
    "STARTUP_RAMP",
    "LEVEL_DECEPTION",
    "MASS_BALANCE_DIVERGENCE",
    "TRUST_QUARANTINE",
    "VERIFICATION_REQUIRED",
    "HANDOVER_BLOCKED",
]


def _base_state(plant_id: str) -> dict:
    now = time.time()
    return {
        "plant_id": plant_id,
        "mode": "simulator_training",
        "phase": "NORMAL_BASELINE",
        "phase_index": 0,
        "phase_count": len(PHASES),
        "started_at": now,
        "updated_at": now,
        "scenario_name": "Simulator baseline",
        "active": False,
        "simulator_source": "read_only_software_simulator",
        "read_only_boundary": (
            "Scenario controls affect only the ConfidenceOS software simulator. "
            "No plant control command, setpoint, mode, or alarm acknowledgement is written."
        ),
        "operator_story": [
            "Normal operation",
            "Mode inferred",
            "Level indication loses trust",
            "Mass-balance contradiction collapses alarms",
            "Operator receives one safe move",
            "Verification and handover debt are created",
        ],
    }


def get_demo_state(plant_id: str, plant=None, loop_status: dict | None = None) -> dict:
    """Return frontend-friendly demo state with live simulator facts attached."""
    state = dict(_DEMO_STATE.get(plant_id) or _base_state(plant_id))
    now = time.time()
    elapsed = None
    active_failures = []
    tick_count = None
    if plant is not None:
        provider = getattr(plant, "tag_provider", None)
        simulator = getattr(plant, "simulator", None)
        if provider and hasattr(provider, "elapsed"):
            try:
                elapsed = round(float(provider.elapsed()), 1)
            except Exception:
                elapsed = None
        if provider and hasattr(provider, "tick_count"):
            tick_count = getattr(provider, "tick_count", None)
        if simulator is not None:
            active_failures = [_failure_summary(item) for item in getattr(simulator, "failures", [])]
        context = getattr(plant, "latest_context", {}) or {}
        mb = getattr(plant, "latest_mb_state", {}) or {}
        confidence = getattr(plant, "latest_confidence", {}) or {}
        verification_tasks = list(getattr(plant, "verification_tokens", []) or [])
        active_failure_count = len(getattr(simulator, "failures", []) if simulator is not None else [])
        verification_status = _verification_status(verification_tasks)
        observed_phase = _observed_phase(
            active=bool(state.get("active")),
            active_failure_count=active_failure_count,
            active_failures=active_failures,
            confidence=confidence,
            mass_balance=mb,
            context=context,
            startup_active=bool(getattr(getattr(plant, "startup_manager", None), "is_active", False)),
        )
        stored_phase = state.get("phase", "NORMAL_BASELINE")
        state["observed_phase"] = observed_phase
        state["phase"] = _furthest_phase(stored_phase, observed_phase) if state.get("active") or active_failure_count else observed_phase
        state["phase_source"] = "training_step" if state["phase"] != observed_phase else "live_evidence"
        state["phase_index"] = PHASES.index(state["phase"]) if state["phase"] in PHASES else 0
        state["verification_status"] = verification_status
        state["trust_recovery_status"] = _trust_recovery_status(
            confidence_by_id=confidence,
            verification_status=verification_status,
            active_failure_count=active_failure_count,
        )
        state["workflow_effects"] = _workflow_effects(state["phase"], verification_status)

    state.update({
        "elapsed_seconds": elapsed,
        "tick_count": tick_count,
        "active_failures": active_failures,
        "active_failure_count": len(active_failures),
        "stream_status": (loop_status or {}).get("status", "unknown"),
        "last_tick": (loop_status or {}).get("last_tick"),
        "persistence_status": (loop_status or {}).get("persistence_status"),
        "now": now,
        "next_operator_action": _next_action(state.get("phase")),
        "lifecycle": _lifecycle_for_phase(state.get("phase")),
    })
    return state


def reset_demo(plant_id: str, plant) -> dict:
    """Reset the simulator to a clean baseline without touching plant controls."""
    _clear_simulator(plant)
    if getattr(plant, "startup_manager", None):
        plant.startup_manager.deactivate()
    _clear_cached_state(plant)
    state = _base_state(plant_id)
    state["scenario_name"] = "Normal baseline - no injected trust failure"
    _DEMO_STATE[plant_id] = state
    return get_demo_state(plant_id, plant)


def start_abnormal_situation(plant_id: str, plant) -> dict:
    """Start the deterministic PRD story in the simulator."""
    _clear_simulator(plant)
    if getattr(plant, "startup_manager", None):
        plant.startup_manager.activate()
    simulator = getattr(plant, "simulator", None)
    if simulator is None:
        raise ValueError("Simulator scenario controls require the software simulator provider.")

    simulator.failures.extend([
        FailureConfig(
            sensor_id="LT-5100",
            failure_type="stuck_reading",
            start_time=0.0,
            stuck_duration=0.0,
        ),
        FailureConfig(
            sensor_id="ZT-6100",
            failure_type="command_state_decoupling",
            start_time=0.0,
            commanded_value=0.0,
            actual_value=100.0,
        ),
        FailureConfig(
            sensor_id="TT-4100",
            failure_type="calibration_drift",
            start_time=0.0,
            drift_rate=0.35,
        ),
    ])
    state = _base_state(plant_id)
    state.update({
        "active": True,
        "phase": "LEVEL_DECEPTION",
        "phase_index": PHASES.index("LEVEL_DECEPTION"),
        "scenario_name": "Hidden level deception and flow contradiction",
        "started_at": time.time(),
        "updated_at": time.time(),
    })
    _DEMO_STATE[plant_id] = state
    return get_demo_state(plant_id, plant)


def advance_demo(plant_id: str, plant) -> dict:
    """Advance the simulator scenario. Currently starts the abnormal story if not active."""
    current = _DEMO_STATE.get(plant_id) or _base_state(plant_id)
    if not current.get("active"):
        return start_abnormal_situation(plant_id, plant)
    current_phase = current.get("phase", "NORMAL_BASELINE")
    index = min(PHASES.index(current_phase) + 1 if current_phase in PHASES else 1, len(PHASES) - 1)
    current["phase"] = PHASES[index]
    current["phase_index"] = index
    current["updated_at"] = time.time()
    _DEMO_STATE[plant_id] = current
    return get_demo_state(plant_id, plant)


def _clear_simulator(plant) -> None:
    simulator = getattr(plant, "simulator", None)
    if simulator is not None:
        simulator.failures.clear()
    provider = getattr(plant, "tag_provider", None)
    if provider is not None:
        provider.reset()
    if getattr(plant, "mass_balance_engine", None):
        plant.mass_balance_engine.reset()


def _clear_cached_state(plant) -> None:
    plant.latest_confidence = {}
    plant.latest_mb_state = {}
    plant.latest_readings = []
    plant.latest_mode_payload = {}
    plant.latest_context = {}
    plant.latest_inferred_mode = {}
    plant.latest_incidents = []
    plant.latest_incident_timeline = []
    plant.latest_new_anomalies = []
    plant.latest_handover_debt = {}
    plant.latest_confidence_debt = []


def _failure_summary(failure: FailureConfig) -> dict:
    payload = asdict(failure)
    return {
        "sensor_id": payload.get("sensor_id"),
        "failure_type": payload.get("failure_type"),
        "start_time": payload.get("start_time"),
        "operator_label": _failure_label(payload),
    }


def _failure_label(payload: dict) -> str:
    sensor = payload.get("sensor_id")
    failure_type = payload.get("failure_type")
    if sensor == "LT-5100" and failure_type == "stuck_reading":
        return "Primary level indication frozen while inventory changes"
    if sensor == "ZT-6100" and failure_type == "command_state_decoupling":
        return "Valve indication disagrees with physical feed effect"
    if failure_type == "calibration_drift":
        return f"{sensor} calibration drift"
    return f"{sensor} {failure_type}"


def _has_quarantined_signal(confidence_by_id: dict) -> bool:
    return any(
        (item or {}).get("trust_state") == "QUARANTINED"
        for item in (confidence_by_id or {}).values()
    )


def _observed_phase(
    *,
    active: bool,
    active_failure_count: int,
    active_failures: list[dict],
    confidence: dict,
    mass_balance: dict,
    context: dict,
    startup_active: bool,
) -> str:
    if _has_quarantined_signal(confidence):
        return "TRUST_QUARANTINE"
    if mass_balance.get("flags") or []:
        return "MASS_BALANCE_DIVERGENCE"
    if context.get("status") in ("WARNING", "CRITICAL"):
        return "LEVEL_DECEPTION"
    if active_failure_count:
        failure_types = {item.get("failure_type") for item in active_failures or []}
        affected = {item.get("sensor_id") for item in active_failures or []}
        if {"FI-2010", "FO-2020"} & affected or "sg_mismatch" in failure_types:
            return "MASS_BALANCE_DIVERGENCE"
        if "stuck_reading" in failure_types or "command_state_decoupling" in failure_types:
            return "LEVEL_DECEPTION"
        if "calibration_drift" in failure_types:
            return "VERIFICATION_REQUIRED"
    if active:
        return "LEVEL_DECEPTION"
    if startup_active:
        return "STARTUP_RAMP"
    return "NORMAL_BASELINE"


def _furthest_phase(stored_phase: str | None, observed_phase: str | None) -> str:
    stored_index = PHASES.index(stored_phase) if stored_phase in PHASES else 0
    observed_index = PHASES.index(observed_phase) if observed_phase in PHASES else 0
    return PHASES[max(stored_index, observed_index)]


def _next_action(phase: str | None) -> str:
    if phase in ("NORMAL_BASELINE", None):
        return "Start an abnormal simulator scenario when training or evaluation begins."
    if phase in ("STARTUP_RAMP", "LEVEL_DECEPTION"):
        return "Watch for mass-balance evidence to contradict the level indication."
    if phase in ("MASS_BALANCE_DIVERGENCE", "TRUST_QUARANTINE"):
        return "Verify level locally before increasing feed or accepting handover."
    if phase == "VERIFICATION_REQUIRED":
        return "Maintenance advances the field verification task."
    return "Manager reviews unresolved handover debt before accepting the shift."


def _verification_status(tasks: list[dict]) -> dict:
    active = [task for task in tasks if task.get("active") or task.get("handover_required")]
    states = [task.get("state") for task in tasks if task.get("state")]
    accepted = [task for task in tasks if task.get("state") == "ACCEPTED"]
    field_done = [task for task in tasks if task.get("state") == "FIELD_CHECK_DONE"]
    return {
        "active_count": len(active),
        "latest_state": states[0] if states else "NONE",
        "accepted_count": len(accepted),
        "field_check_done_count": len(field_done),
        "handover_blocked_by_verification": any(task.get("handover_required") for task in active),
    }


def _trust_recovery_status(confidence_by_id: dict, verification_status: dict, active_failure_count: int) -> str:
    quarantined = _has_quarantined_signal(confidence_by_id)
    if verification_status.get("accepted_count") and active_failure_count:
        return "field_verified_instrument_repair_required"
    if verification_status.get("accepted_count") and not quarantined:
        return "field_verified_trust_recovered"
    if verification_status.get("field_check_done_count"):
        return "field_evidence_waiting_acceptance"
    if verification_status.get("active_count"):
        return "field_verification_required"
    if quarantined:
        return "trust_quarantine_active"
    return "normal_monitoring"


def _workflow_effects(phase: str | None, verification_status: dict) -> list[str]:
    effects = []
    if phase in ("MASS_BALANCE_DIVERGENCE", "TRUST_QUARANTINE", "VERIFICATION_REQUIRED", "HANDOVER_BLOCKED"):
        effects.extend([
            "Runtime promotes operating basis and action contract.",
            "Work Queue owns field verification and confidence debt.",
            "Shift Channel pins unresolved handover debt until workflow clears.",
        ])
    if verification_status.get("accepted_count"):
        effects.append("Accepted field evidence is retained as audit evidence but does not override confidence scoring.")
    return effects or ["Runtime remains in normal monitoring mode."]


def _lifecycle_for_phase(phase: str | None) -> dict:
    catalog = {
        "NORMAL_BASELINE": {
            "stage": "normal_monitoring",
            "expected_system_response": "Runtime shows generated faceplates and no active operating-basis exception.",
            "recovery_condition": "No action required.",
        },
        "STARTUP_RAMP": {
            "stage": "context_detection",
            "expected_system_response": "Mode inference tightens startup confidence and mass-balance interpretation.",
            "recovery_condition": "Startup mode clears and readings remain consistent.",
        },
        "LEVEL_DECEPTION": {
            "stage": "confidence_degradation",
            "expected_system_response": "Primary indication is watched for cross-sensor contradiction.",
            "recovery_condition": "Sensor resumes tracking process physics or verification is requested.",
        },
        "MASS_BALANCE_DIVERGENCE": {
            "stage": "alarm_collapse",
            "expected_system_response": "Raw warnings collapse into one operating question.",
            "recovery_condition": "Mass-balance contradiction clears or trusted substitute is established.",
        },
        "TRUST_QUARANTINE": {
            "stage": "decision_freeze",
            "expected_system_response": "Quarantined signal remains visible but cannot be used as decision basis.",
            "recovery_condition": "Manual verification is accepted and confidence recovers from deterministic evidence.",
        },
        "VERIFICATION_REQUIRED": {
            "stage": "field_workflow",
            "expected_system_response": "Maintenance receives a field verification task.",
            "recovery_condition": "Field check evidence is accepted or task expires and remains handover debt.",
        },
        "HANDOVER_BLOCKED": {
            "stage": "shift_continuity",
            "expected_system_response": "Manager/Auditor sees handover blocked until unresolved verification debt clears.",
            "recovery_condition": "Verification is accepted or explicitly carried into next shift.",
        },
    }
    return catalog.get(phase or "NORMAL_BASELINE", catalog["NORMAL_BASELINE"])
