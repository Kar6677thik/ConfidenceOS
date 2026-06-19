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
        active_failure_count = len(getattr(simulator, "failures", []) if simulator is not None else [])
        if _has_quarantined_signal(confidence):
            state["phase"] = "TRUST_QUARANTINE"
        elif (mb.get("flags") or []):
            state["phase"] = "MASS_BALANCE_DIVERGENCE"
        elif context.get("status") in ("WARNING", "CRITICAL"):
            state["phase"] = "LEVEL_DECEPTION"
        elif state.get("active") and active_failure_count:
            state["phase"] = "LEVEL_DECEPTION"
        elif getattr(getattr(plant, "startup_manager", None), "is_active", False):
            state["phase"] = "STARTUP_RAMP"
        state["phase_index"] = PHASES.index(state["phase"]) if state["phase"] in PHASES else 0

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
    })
    return state


def reset_demo(plant_id: str, plant) -> dict:
    """Reset the simulator to a clean baseline for a judge."""
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


def _next_action(phase: str | None) -> str:
    if phase in ("NORMAL_BASELINE", None):
        return "Start abnormal situation demo when the judge is ready."
    if phase in ("STARTUP_RAMP", "LEVEL_DECEPTION"):
        return "Watch for mass-balance evidence to contradict the level indication."
    if phase in ("MASS_BALANCE_DIVERGENCE", "TRUST_QUARANTINE"):
        return "Verify level locally before increasing feed or accepting handover."
    if phase == "VERIFICATION_REQUIRED":
        return "Maintenance advances the field verification task."
    return "Manager reviews unresolved handover debt before accepting the shift."
