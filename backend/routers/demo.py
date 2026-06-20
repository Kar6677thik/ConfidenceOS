"""
routers/demo.py — Scenario control, simulation controls, demo alias endpoints,
and live failure injection.

All routes are behaviour-preserving extractions from main.py; no logic changed.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from demo_service import advance_demo, get_demo_state, reset_demo, start_abnormal_situation
from shift_channel import reset_notes as reset_shift_notes
from asset_model import active_asset_model_key
from studio_service import (
    reset as studio_reset,
    select_asset_model as studio_select_asset_model,
)
from deps import plant_manager, plant_loop_status
from auth import require_role

router = APIRouter()

SCENARIO_DIR = Path(__file__).parent.parent
ALLOWED_SCENARIOS = {"scenario.json", "scenario_b.json", "scenario_c.json"}

_VALID_FAILURE_TYPES = {
    "calibration_drift", "stuck_reading", "sg_mismatch", "command_state_decoupling",
}


class SimInjectRequest(BaseModel):
    """Inject one failure into the LIVE simulator source."""
    plant_id: str = "plant-a"
    sensor_id: str
    failure_type: str
    drift_rate: Optional[float] = None
    stuck_duration: Optional[float] = None
    sg_actual: Optional[float] = None
    sg_calibrated: Optional[float] = None
    commanded_value: Optional[float] = None
    actual_value: Optional[float] = None


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


# ─── Scenario control ────────────────────────────────────────────────────────

@router.post("/api/scenario/load", dependencies=[Depends(require_role("Engineer", "Manager"))])
def load_scenario(scenario_path: Optional[str] = None, plant_id: str = Query(default="plant-a")):
    """Load a failure injection scenario."""
    plant = plant_manager.get(plant_id)
    path = _resolve_scenario_path(scenario_path)
    plant.tag_provider.load_scenario(path)
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    return {"status": "loaded", "scenario": path.name}


@router.post("/api/scenario/reset", dependencies=[Depends(require_role("Engineer", "Manager"))])
def reset_scenario(plant_id: str = Query(default="plant-a")):
    """Reset the simulator clock and state."""
    plant = plant_manager.get(plant_id)
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    return {"status": "reset"}


# ─── Simulation controls ─────────────────────────────────────────────────────

@router.get("/api/simulation/state")
def get_simulation_state(plant_id: str = Query(default="plant-a")):
    """Return simulator scenario phase and source facts."""
    plant = plant_manager.get(plant_id)
    return get_demo_state(plant_id, plant, plant_loop_status.get(plant_id, {}))


@router.post("/api/simulation/reset-source", dependencies=[Depends(require_role("Engineer", "Manager"))])
def reset_simulation_source(plant_id: str = Query(default="plant-a")):
    """Reset only the simulator source and scenario state."""
    plant = _require_simulator_plant(plant_id)
    state = reset_demo(plant_id, plant)
    return {"status": "reset", "simulation_state": state, "demo_state": state}


@router.post("/api/simulation/start-abnormal-situation", dependencies=[Depends(require_role("Engineer", "Manager"))])
def start_simulation_abnormal_situation(plant_id: str = Query(default="plant-a")):
    """Start the abnormal simulator scenario without changing Studio state."""
    plant = _require_simulator_plant(plant_id)
    state = start_abnormal_situation(plant_id, plant)
    return {"status": "started", "simulation_state": state, "demo_state": state}


@router.post("/api/simulation/advance", dependencies=[Depends(require_role("Engineer", "Manager"))])
def advance_simulation_scenario(plant_id: str = Query(default="plant-a")):
    """Advance the simulator scenario phase without writing plant controls."""
    plant = _require_simulator_plant(plant_id)
    state = advance_demo(plant_id, plant)
    return {"status": "advanced", "simulation_state": state, "demo_state": state}


# ─── Demo alias endpoints ────────────────────────────────────────────────────

@router.get("/api/demo/state")
def get_judge_demo_state(plant_id: str = Query(default="plant-a")):
    """Compatibility alias for simulator scenario state."""
    plant = plant_manager.get(plant_id)
    return get_demo_state(plant_id, plant, plant_loop_status.get(plant_id, {}))


@router.post("/api/demo/reset", dependencies=[Depends(require_role("Engineer", "Manager"))])
def reset_judge_demo(plant_id: str = Query(default="plant-a")):
    """Compatibility endpoint: reset the app-wide training baseline."""
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


@router.post("/api/demo/start-abnormal-situation", dependencies=[Depends(require_role("Engineer", "Manager"))])
def start_judge_abnormal_situation(plant_id: str = Query(default="plant-a")):
    """Compatibility endpoint: trigger the trust-quarantine simulator scenario."""
    plant = _require_simulator_plant(plant_id)
    if active_asset_model_key() != "texas_city_vessel":
        studio_select_asset_model("texas_city_vessel")
    state = start_abnormal_situation(plant_id, plant)
    return {"status": "started", "demo_state": state}


@router.post("/api/demo/advance", dependencies=[Depends(require_role("Engineer", "Manager"))])
def advance_judge_demo(plant_id: str = Query(default="plant-a")):
    """Compatibility endpoint: advance the simulator scenario phase without writing plant controls."""
    plant = _require_simulator_plant(plant_id)
    state = advance_demo(plant_id, plant)
    return {"status": "advanced", "demo_state": state}


# ─── Live failure injection ──────────────────────────────────────────────────

@router.post("/api/sim/inject", dependencies=[Depends(require_role("Engineer", "Manager"))])
def sim_inject(request: SimInjectRequest):
    """Inject a single failure into the LIVE simulator."""
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


@router.post("/api/sim/clear", dependencies=[Depends(require_role("Engineer", "Manager"))])
def sim_clear(plant_id: str = Query(default="plant-a")):
    """Clear all injected failures from the LIVE simulator."""
    plant = _require_simulator_plant(plant_id)
    plant.simulator.failures.clear()
    plant.tag_provider.reset()
    plant.mass_balance_engine.reset()
    state = reset_demo(plant_id, plant)
    return {"status": "cleared", "simulation_source_only": True, "active_failures": 0, "simulation_state": state}
