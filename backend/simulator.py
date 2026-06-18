"""
simulator.py — SensorSimulator class for ConfidenceOS.

Generates realistic industrial sensor data streams for 6 sensor types:
  - Level Transmitter (LT)
  - Flow Meter Inflow (FI)
  - Flow Meter Outflow (FO)
  - Pressure Transmitter (PT)
  - Temperature Sensor (TT)
  - Valve Position Indicator (ZT)

Supports configurable failure injection via scenario.json:
  - calibration_drift: reading shifts linearly over time
  - stuck_reading: sensor freezes at last value
  - cross_sensor_divergence: level vs flow disagree beyond tolerance
  - sg_mismatch: specific gravity mismatch (Texas City failure)
  - command_state_decoupling: valve commanded closed but stuck open (TMI failure)
"""

import os
import json
import time
import math
import random
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Optional deterministic seed for reproducible demo runs. Unset = normal random
# behaviour; set CONFIDENCEOS_SIM_SEED to make the noise stream repeatable.
_SIM_SEED = os.getenv("CONFIDENCEOS_SIM_SEED")
if _SIM_SEED is not None:
    try:
        random.seed(int(_SIM_SEED))
    except ValueError:
        random.seed(_SIM_SEED)


# Net-flow → level conversion used to integrate the hidden *actual* vessel level
# from the true (uncorrupted) inflow − outflow. Mirrors MassBalanceEngine's
# FLOW_TO_LEVEL_RATE so the physically-true "actual" and the flow-implied level
# are on the same scale.
FLOW_TO_LEVEL_RATE = 0.005  # ft per (gpm · second)


@dataclass
class SensorConfig:
    """Configuration for a single simulated sensor."""
    sensor_id: str
    sensor_type: str  # level, flow_in, flow_out, pressure, temperature, valve
    unit: str
    base_value: float
    noise_std: float  # Gaussian noise standard deviation
    min_value: float
    max_value: float
    # Slow sinusoidal variation to make data look realistic
    variation_amplitude: float = 0.0
    variation_period: float = 300.0  # seconds for one cycle


@dataclass
class FailureConfig:
    """Configuration for a failure injection on a specific sensor."""
    sensor_id: str
    failure_type: str  # calibration_drift, stuck_reading, sg_mismatch, command_state_decoupling
    start_time: float  # seconds from simulation start
    # calibration_drift params
    drift_rate: float = 0.0  # units per second
    # stuck_reading params
    stuck_duration: float = 0.0  # how long to stay stuck (seconds); 0 = forever
    # sg_mismatch params
    sg_actual: float = 1.0
    sg_calibrated: float = 1.0
    # command_state_decoupling params
    commanded_value: float = 0.0  # what the command says
    actual_value: float = 100.0  # what the valve physically is


@dataclass
class SensorReading:
    """A single reading emitted by the simulator.

    `value` is the *indicated* reading — what the HMI/sensor reports, including
    any failure corruption (frozen, scaled, drifted, decoupled). `actual_value`
    is the hidden *physically-true* state the sensor is supposed to observe.
    In healthy operation the two track each other; a failure makes them diverge.
    This gap is the heart of ConfidenceOS: "the number on screen may be wrong."
    """
    sensor_id: str
    sensor_type: str
    value: float
    unit: str
    timestamp: float
    failure_mode: Optional[str] = None
    actual_value: Optional[float] = None


# ─── Default Sensor Configurations ───────────────────────────────────────────

DEFAULT_SENSORS = [
    SensorConfig(
        sensor_id="LT-5100",
        sensor_type="level",
        unit="ft",
        base_value=50.0,
        noise_std=0.3,
        min_value=0.0,
        max_value=200.0,
        variation_amplitude=5.0,
        variation_period=600.0,
    ),
    SensorConfig(
        sensor_id="FI-2010",
        sensor_type="flow_in",
        unit="gpm",
        # Net inflow runs ~+14 gpm over outflow: the vessel is genuinely filling,
        # so the *physical* level rises. While the level sensor is healthy it
        # tracks that rise; once it freezes, physics (flow) and the frozen
        # reading diverge — the Texas City overfill signature.
        base_value=132.0,
        noise_std=2.0,
        min_value=0.0,
        max_value=500.0,
        variation_amplitude=10.0,
        variation_period=480.0,
    ),
    SensorConfig(
        sensor_id="FO-2020",
        sensor_type="flow_out",
        unit="gpm",
        base_value=118.0,
        noise_std=2.0,
        min_value=0.0,
        max_value=500.0,
        variation_amplitude=8.0,
        variation_period=520.0,
    ),
    SensorConfig(
        sensor_id="PT-3100",
        sensor_type="pressure",
        unit="psi",
        base_value=21.0,
        noise_std=0.2,
        min_value=0.0,
        max_value=100.0,
        variation_amplitude=1.5,
        variation_period=700.0,
    ),
    SensorConfig(
        sensor_id="TT-4100",
        sensor_type="temperature",
        unit="°F",
        base_value=350.0,
        noise_std=1.0,
        min_value=60.0,
        max_value=800.0,
        variation_amplitude=8.0,
        variation_period=900.0,
    ),
    SensorConfig(
        sensor_id="ZT-6100",
        sensor_type="valve",
        # Feed control valve. Its base value is the nominal commanded position
        # during steady feed (a throttling valve sits part-open, not at 0%). The
        # true inflow is derived from the valve's *actual* position, so a valve
        # that is commanded closed but physically open keeps filling the vessel.
        unit="%",
        base_value=60.0,
        noise_std=0.1,
        min_value=0.0,
        max_value=100.0,
        variation_amplitude=0.0,  # valves don't naturally vary
        variation_period=1.0,
    ),
]


class SensorSimulator:
    """
    Generates realistic industrial sensor readings at 1 Hz.
    
    Usage:
        sim = SensorSimulator()
        sim.load_scenario("scenario.json")  # optional failure injection
        readings = sim.tick()  # call once per second
    """

    def __init__(self, sensors: list[SensorConfig] | None = None):
        self.sensors = {s.sensor_id: s for s in (sensors or DEFAULT_SENSORS)}
        self.failures: list[FailureConfig] = []
        self.start_time = time.time()
        self.tick_count = 0

        # Per-sensor state for failure injection
        self._stuck_values: dict[str, float] = {}
        self._stuck_start: dict[str, float] = {}
        self._last_values: dict[str, float] = {}

        # Hidden physically-true vessel level, integrated from the *true*
        # (uncorrupted) net flow. This is the ground truth the level sensor is
        # meant to observe; it keeps moving even when the indicated reading lies.
        self._actual_level: Optional[float] = None
        self._prev_actual_time: Optional[float] = None

        # True feed-valve position (%). Drives the true inflow each tick. Normally
        # equals the commanded/nominal position; a command_state_decoupling failure
        # forces it away from the command so an "operator-closed" valve can still
        # be physically open and keep filling the vessel.
        self._valve_actual_pct: Optional[float] = None

    def load_scenario(self, path: str | Path) -> None:
        """Load failure injection scenario from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        self.failures = []
        for entry in data.get("failures", []):
            self.failures.append(FailureConfig(**entry))

    def elapsed(self) -> float:
        """Seconds since simulation started."""
        return time.time() - self.start_time

    def reset(self) -> None:
        """Reset simulation clock and state."""
        self.start_time = time.time()
        self.tick_count = 0
        self._stuck_values.clear()
        self._stuck_start.clear()
        self._last_values.clear()
        self._actual_level = None
        self._prev_actual_time = None
        self._valve_actual_pct = None

    def tick(self) -> list[dict]:
        """
        Generate one reading per sensor. Call this at 1 Hz.
        Returns a list of reading dicts ready for JSON serialization.
        """
        now = time.time()
        elapsed = now - self.start_time
        self.tick_count += 1
        readings = []

        # 0. Resolve the true feed-valve position for this tick (honours a
        #    command_state_decoupling failure). The true inflow is a function of
        #    this, so the process — not just a tag — responds when the valve lies.
        valve_actual, valve_nominal = self._compute_valve_actual(elapsed)

        # 1. Compute the uncorrupted, physically-true base value for every
        #    non-level sensor. Inflow is derived from the actual valve position
        #    (feed valve), so opening the valve genuinely increases inflow.
        base_values: dict[str, float] = {}
        for sensor_id, config in self.sensors.items():
            if config.sensor_type == "level":
                continue
            if config.sensor_type == "flow_in" and valve_actual is not None and valve_nominal:
                noise = random.gauss(0, config.noise_std)
                base_values[sensor_id] = config.base_value * (valve_actual / valve_nominal) + noise
            else:
                base_values[sensor_id] = self._base_value(config, elapsed)

        # 2. Integrate the hidden actual vessel level from the TRUE net flow
        #    (uncorrupted inflow − outflow), independent of what any sensor reports.
        self._integrate_actual_level(base_values, now)

        # 3. The level sensor's *true* reading tracks the integrated physical
        #    level (plus sensor noise) — so a healthy LT follows physics, and a
        #    failed LT visibly departs from it.
        for sensor_id, config in self.sensors.items():
            if config.sensor_type == "level":
                truth = self._actual_level if self._actual_level is not None else config.base_value
                base_values[sensor_id] = truth + random.gauss(0, config.noise_std)

        # 4. Resolve indicated (possibly corrupted) value + hidden actual per sensor.
        for sensor_id, config in self.sensors.items():
            base_reading = base_values[sensor_id]
            actual_truth = self._actual_level if (
                config.sensor_type == "level" and self._actual_level is not None
            ) else base_reading

            indicated, failure_mode, actual_override = self._resolve_indicated(
                config, base_reading, elapsed
            )
            if actual_override is not None:
                actual_truth = actual_override

            # Clamp both to physical limits
            indicated = max(config.min_value, min(config.max_value, indicated))
            actual_truth = max(config.min_value, min(config.max_value, actual_truth))
            self._last_values[sensor_id] = indicated

            reading = SensorReading(
                sensor_id=sensor_id,
                sensor_type=config.sensor_type,
                value=round(indicated, 2),
                unit=config.unit,
                timestamp=now,
                failure_mode=failure_mode,
                actual_value=round(actual_truth, 2),
            )
            readings.append(asdict(reading))

        return readings

    def _base_value(self, config: SensorConfig, elapsed: float) -> float:
        """Uncorrupted realistic value: base + sinusoidal variation + Gaussian noise."""
        variation = config.variation_amplitude * math.sin(
            2 * math.pi * elapsed / config.variation_period
        )
        noise = random.gauss(0, config.noise_std)
        return config.base_value + variation + noise

    def _integrate_actual_level(self, base_values: dict[str, float], now: float) -> None:
        """Advance the hidden physical vessel level from the true net flow.

        Uses the *uncorrupted* flow base values (not the indicated readings), so
        the actual level keeps moving even when a flow transmitter is frozen.
        """
        level_config = next(
            (c for c in self.sensors.values() if c.sensor_type == "level"), None
        )
        if level_config is None:
            return

        if self._actual_level is None:
            self._actual_level = level_config.base_value
            self._prev_actual_time = now
            return

        inflow = sum(
            v for sid, v in base_values.items()
            if self.sensors[sid].sensor_type == "flow_in"
        )
        outflow = sum(
            v for sid, v in base_values.items()
            if self.sensors[sid].sensor_type == "flow_out"
        )
        dt = max(0.0, now - (self._prev_actual_time or now))
        self._prev_actual_time = now
        net_flow = inflow - outflow  # gpm
        self._actual_level += net_flow * FLOW_TO_LEVEL_RATE * dt
        self._actual_level = max(
            level_config.min_value, min(level_config.max_value, self._actual_level)
        )

    def _compute_valve_actual(self, elapsed: float) -> tuple[Optional[float], Optional[float]]:
        """Return ``(actual_pct, nominal_pct)`` for the feed valve this tick.

        Nominal is the commanded/steady position (the valve config base). A
        command_state_decoupling failure forces the *actual* position away from
        the command, so the true inflow diverges from what the operator sees.
        Returns ``(None, None)`` when the model has no valve.
        """
        valve_cfg = next((c for c in self.sensors.values() if c.sensor_type == "valve"), None)
        if valve_cfg is None:
            self._valve_actual_pct = None
            return None, None
        nominal = valve_cfg.base_value
        actual = nominal
        for f in self._get_active_failures(valve_cfg.sensor_id, elapsed):
            if f.failure_type == "command_state_decoupling":
                actual = f.actual_value
        self._valve_actual_pct = actual
        return actual, nominal

    def _get_active_failures(self, sensor_id: str, elapsed: float) -> list[FailureConfig]:
        """Return all active failures for a sensor, ordered by start_time.

        Multiple failures on one sensor compose deterministically (see
        ``_resolve_indicated``) instead of only the first one applying.
        """
        active = []
        for f in self.failures:
            if f.sensor_id == sensor_id and elapsed >= f.start_time:
                # A stuck_reading with a finite duration expires.
                if f.failure_type == "stuck_reading" and f.stuck_duration > 0:
                    if elapsed > f.start_time + f.stuck_duration:
                        continue
                active.append(f)
        active.sort(key=lambda f: f.start_time)
        return active

    # Reported-mode precedence when several failures are active on one sensor.
    _MODE_PRECEDENCE = ("stuck_reading", "command_state_decoupling", "sg_mismatch", "calibration_drift")

    def _resolve_indicated(
        self,
        config: SensorConfig,
        base_reading: float,
        elapsed: float,
    ) -> tuple[float, Optional[str], Optional[float]]:
        """Resolve the *indicated* reading for this tick, composing all active failures.

        Returns ``(indicated_value, failure_mode, actual_override)``. Corruptions
        compose in start-time order (drift then SG scaling), then terminal
        overrides apply (decoupling replaces the value; stuck freezes it). The
        reported ``failure_mode`` follows ``_MODE_PRECEDENCE`` so downstream logic
        that keys on e.g. ``stuck_reading`` still sees it. ``actual_override`` is
        set only when a failure defines a physical truth (decoupled valve).
        """
        failures = self._get_active_failures(config.sensor_id, elapsed)

        if not failures:
            # Clear stuck state if no longer active
            self._stuck_values.pop(config.sensor_id, None)
            self._stuck_start.pop(config.sensor_id, None)
            return base_reading, None, None

        value = base_reading
        actual_override = None
        modes = []

        # 1. Non-terminal corruptions, in start-time order.
        for f in failures:
            if f.failure_type == "calibration_drift":
                value += f.drift_rate * (elapsed - f.start_time)
                modes.append("calibration_drift")
            elif f.failure_type == "sg_mismatch":
                value *= (f.sg_calibrated / f.sg_actual)
                modes.append("sg_mismatch")

        # 2. Command-state decoupling: HMI shows command, valve is elsewhere.
        decoup = next((f for f in failures if f.failure_type == "command_state_decoupling"), None)
        if decoup is not None:
            value = decoup.commanded_value
            actual_override = decoup.actual_value
            modes.append("command_state_decoupling")

        # 3. Stuck freezes the (possibly already-corrupted) last emitted value.
        stuck = next((f for f in failures if f.failure_type == "stuck_reading"), None)
        if stuck is not None:
            sid = config.sensor_id
            if sid not in self._stuck_values:
                self._stuck_values[sid] = self._last_values.get(sid, value)
                self._stuck_start[sid] = elapsed
            value = self._stuck_values[sid]
            modes.append("stuck_reading")

        primary = next((m for m in self._MODE_PRECEDENCE if m in modes), None)
        return value, primary, actual_override
