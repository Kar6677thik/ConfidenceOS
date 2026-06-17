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

import json
import time
import math
import random
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


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
        unit="%",
        base_value=0.0,  # 0% = fully closed, 100% = fully open
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

    def tick(self) -> list[dict]:
        """
        Generate one reading per sensor. Call this at 1 Hz.
        Returns a list of reading dicts ready for JSON serialization.
        """
        now = time.time()
        elapsed = now - self.start_time
        self.tick_count += 1
        readings = []

        # 1. Compute the uncorrupted, physically-true base value for every
        #    non-level sensor first (the level is derived from integrated flow).
        base_values: dict[str, float] = {}
        for sensor_id, config in self.sensors.items():
            if config.sensor_type == "level":
                continue
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

    def _get_active_failure(self, sensor_id: str, elapsed: float) -> Optional[FailureConfig]:
        """Find the active failure for a sensor at the current time, if any."""
        for f in self.failures:
            if f.sensor_id == sensor_id and elapsed >= f.start_time:
                # Check if stuck_reading has expired
                if f.failure_type == "stuck_reading" and f.stuck_duration > 0:
                    if elapsed > f.start_time + f.stuck_duration:
                        continue
                return f
        return None

    def _resolve_indicated(
        self,
        config: SensorConfig,
        base_reading: float,
        elapsed: float,
    ) -> tuple[float, Optional[str], Optional[float]]:
        """Resolve the *indicated* reading for this tick, applying any active failure.

        Returns ``(indicated_value, failure_mode, actual_override)``. The
        ``actual_override`` is only set when the failure defines a physical truth
        that differs from this sensor's base reading (e.g. a decoupled valve whose
        real position is known); otherwise the caller's actual truth is used.
        """
        failure = self._get_active_failure(config.sensor_id, elapsed)

        if failure is None:
            # Clear stuck state if no longer active
            self._stuck_values.pop(config.sensor_id, None)
            self._stuck_start.pop(config.sensor_id, None)
            return base_reading, None, None

        time_in_failure = elapsed - failure.start_time

        if failure.failure_type == "calibration_drift":
            # Indicated drifts linearly away from the true value.
            drift = failure.drift_rate * time_in_failure
            return base_reading + drift, "calibration_drift", None

        elif failure.failure_type == "stuck_reading":
            # Indicated freezes at the last value before the failure started,
            # while the actual (base / integrated level) keeps moving.
            sid = config.sensor_id
            if sid not in self._stuck_values:
                self._stuck_values[sid] = self._last_values.get(sid, base_reading)
                self._stuck_start[sid] = elapsed
            return self._stuck_values[sid], "stuck_reading", None

        elif failure.failure_type == "sg_mismatch":
            # Indicated reads value scaled by the wrong specific-gravity ratio.
            scale = failure.sg_calibrated / failure.sg_actual
            return base_reading * scale, "sg_mismatch", None

        elif failure.failure_type == "command_state_decoupling":
            # HMI shows the commanded position; the valve is physically elsewhere.
            return failure.commanded_value, "command_state_decoupling", failure.actual_value

        else:
            return base_reading, None, None
