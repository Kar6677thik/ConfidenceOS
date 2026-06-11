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
    """A single reading emitted by the simulator."""
    sensor_id: str
    sensor_type: str
    value: float
    unit: str
    timestamp: float
    failure_mode: Optional[str] = None


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
        base_value=120.0,
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

    def tick(self) -> list[dict]:
        """
        Generate one reading per sensor. Call this at 1 Hz.
        Returns a list of reading dicts ready for JSON serialization.
        """
        now = time.time()
        elapsed = now - self.start_time
        self.tick_count += 1
        readings = []

        for sensor_id, config in self.sensors.items():
            value, failure_mode = self._generate_reading(config, elapsed)
            # Clamp to physical limits
            value = max(config.min_value, min(config.max_value, value))
            self._last_values[sensor_id] = value

            reading = SensorReading(
                sensor_id=sensor_id,
                sensor_type=config.sensor_type,
                value=round(value, 2),
                unit=config.unit,
                timestamp=now,
                failure_mode=failure_mode,
            )
            readings.append(asdict(reading))

        return readings

    def _generate_reading(self, config: SensorConfig, elapsed: float) -> tuple[float, Optional[str]]:
        """Generate a single sensor reading, applying any active failures."""

        # Base realistic value: base + sinusoidal variation + Gaussian noise
        variation = config.variation_amplitude * math.sin(
            2 * math.pi * elapsed / config.variation_period
        )
        noise = random.gauss(0, config.noise_std)
        base_reading = config.base_value + variation + noise

        # Check for active failures on this sensor
        active_failure = self._get_active_failure(config.sensor_id, elapsed)

        if active_failure is None:
            # Clear stuck state if no longer active
            self._stuck_values.pop(config.sensor_id, None)
            self._stuck_start.pop(config.sensor_id, None)
            return base_reading, None

        return self._apply_failure(config, base_reading, active_failure, elapsed)

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

    def _apply_failure(
        self,
        config: SensorConfig,
        base_reading: float,
        failure: FailureConfig,
        elapsed: float,
    ) -> tuple[float, str]:
        """Apply a failure mode to the base reading."""
        time_in_failure = elapsed - failure.start_time

        if failure.failure_type == "calibration_drift":
            # Reading drifts linearly from true value
            drift = failure.drift_rate * time_in_failure
            return base_reading + drift, "calibration_drift"

        elif failure.failure_type == "stuck_reading":
            # Freeze at the last value before the failure started
            sid = config.sensor_id
            if sid not in self._stuck_values:
                self._stuck_values[sid] = self._last_values.get(sid, base_reading)
                self._stuck_start[sid] = elapsed
            return self._stuck_values[sid], "stuck_reading"

        elif failure.failure_type == "sg_mismatch":
            # Sensor reads value scaled by wrong specific gravity ratio
            # True level = base_reading, but sensor shows:
            scale = failure.sg_calibrated / failure.sg_actual
            return base_reading * scale, "sg_mismatch"

        elif failure.failure_type == "command_state_decoupling":
            # Valve shows commanded position, not actual position
            # The "value" the HMI shows is the commanded value
            return failure.commanded_value, "command_state_decoupling"

        else:
            return base_reading, None
