"""
mass_balance.py — Configurable single-vessel volumetric residual check (Module 3).

Scope (stated honestly): this is a configurable *single-vessel volumetric residual
check*, not a first-principles process model. It assumes ONE inflow and ONE outflow,
a single linear flow→level conversion factor (`flow_to_level_rate`, per-asset), and no
density / phase / recycle / transport-delay / unmeasured-stream compensation. A process
engineer should read it as "trapezoidal-integrated volumetric balance with a per-vessel
calibration constant," which is exactly what it is.

    implied_level_delta = integral(inflow_rate - outflow_rate, dt) * flow_to_level_rate
    measured_level_delta = current_level - level_at_window_start
    discrepancy = |implied_level_delta - measured_level_delta|

Rolling integration window (default 15 min). Three escalation levels:
    INFO     — discrepancy > tolerance (small divergence detected)
    WARNING  — discrepancy > 2x tolerance (significant divergence)
    CRITICAL — discrepancy > 4x tolerance (large, likely-instrument divergence)
"""

# Honest, UI-surfaceable statement of what this residual check does and does not model.
ASSUMPTIONS = (
    "Single inflow/outflow, linear per-vessel flow→level factor; "
    "no density, phase, recycle, transport-delay, or unmeasured-stream compensation."
)

from dataclasses import dataclass, asdict
from collections import deque
from typing import Optional
import time


# ─── Configuration ───────────────────────────────────────────────────────────

# Default integration window in seconds (15 minutes)
DEFAULT_WINDOW_SECONDS = 900.0

# Default tolerance threshold (accounts for measurement noise)
# In "level units" — the acceptable difference between flow-implied and measured delta
DEFAULT_TOLERANCE = 5.0

# Escalation multipliers: severity = tolerance * multiplier
SEVERITY_MULTIPLIERS = {
    "INFO": 1.0,
    "WARNING": 2.0,
    "CRITICAL": 4.0,
}

# Conversion factor: flow (gpm) to level change rate (ft/s)
# This is vessel-specific. For our demo vessel: 1 gpm ≈ 0.005 ft/s
# (a ~200 gallon cross-section vessel, roughly)
FLOW_TO_LEVEL_RATE = 0.005


# ─── Data types ──────────────────────────────────────────────────────────────

@dataclass
class MassBalanceFlag:
    """A physical inconsistency flag raised by the engine."""
    severity: str           # INFO, WARNING, CRITICAL
    discrepancy: float      # absolute difference in level units
    implied_delta: float    # what flows imply the level change should be
    measured_delta: float   # what the level sensor actually shows
    sensor_ids: list[str]   # sensors involved
    message: str            # human-readable description
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "discrepancy": round(self.discrepancy, 2),
            "implied_delta": round(self.implied_delta, 2),
            "measured_delta": round(self.measured_delta, 2),
            "sensor_ids": self.sensor_ids,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class MassBalanceState:
    """Current state snapshot for the WebSocket stream."""
    implied_level: float       # flow-integrated implied level
    measured_level: float      # what the LT sensor reads (indicated)
    discrepancy: float         # |implied - measured| delta
    implied_delta: float       # total implied level change within window
    measured_delta: float      # total measured level change within window
    flags: list[MassBalanceFlag]
    actual_level: Optional[float] = None  # hidden physically-true level (simulator ground truth)

    def to_dict(self) -> dict:
        return {
            "implied_level": round(self.implied_level, 2),
            "measured_level": round(self.measured_level, 2),
            "discrepancy": round(self.discrepancy, 2),
            "implied_delta": round(self.implied_delta, 2),
            "measured_delta": round(self.measured_delta, 2),
            "flags": [f.to_dict() for f in self.flags],
            "actual_level": round(self.actual_level, 2) if self.actual_level is not None else None,
        }


# ─── Mass-Balance Engine ────────────────────────────────────────────────────

class MassBalanceEngine:
    """
    Continuously integrates inflow/outflow and compares to level sensor.
    Flags violations in real time with escalating severity.

    Usage:
        engine = MassBalanceEngine()
        state = engine.update(readings)  # call once per tick
    """

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        tolerance: float = DEFAULT_TOLERANCE,
        flow_to_level_rate: float = FLOW_TO_LEVEL_RATE,
    ):
        self.window_seconds = window_seconds
        self.tolerance = tolerance
        self.flow_to_level_rate = flow_to_level_rate

        # Time series within the rolling window
        # Each entry: (timestamp, inflow, outflow, level)
        self._history: deque = deque()

        # Running integration of net flow
        self._cumulative_flow_delta: float = 0.0

        # The "anchor" level at the start of the current window
        self._window_start_level: Optional[float] = None
        self._window_start_time: Optional[float] = None

        # Track the implied absolute level (starting from the first measured level)
        self._implied_level: Optional[float] = None

        # Previous tick values for trapezoidal integration
        self._prev_inflow: Optional[float] = None
        self._prev_outflow: Optional[float] = None
        self._prev_time: Optional[float] = None

        # Active flags
        self.active_flags: list[MassBalanceFlag] = []

    def config_dict(self) -> dict:
        """
        Expose the (engineer-owned) residual-check parameters so the UI can show
        them as configurable assumptions rather than hidden magic numbers.
        """
        return {
            "tolerance": round(self.tolerance, 3),
            "flow_to_level_rate": self.flow_to_level_rate,
            "window_seconds": self.window_seconds,
            "method": "trapezoidal volumetric integration (single vessel)",
            "assumptions": ASSUMPTIONS,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._history.clear()
        self._cumulative_flow_delta = 0.0
        self._window_start_level = None
        self._window_start_time = None
        self._implied_level = None
        self._prev_inflow = None
        self._prev_outflow = None
        self._prev_time = None
        self.active_flags.clear()

    def update(self, readings: list[dict]) -> MassBalanceState:
        """
        Process one tick of sensor readings.
        Expects readings list to include sensors of type: level, flow_in, flow_out.

        Returns the current MassBalanceState with implied level, measured level,
        discrepancy, and any active flags.
        """
        # Extract relevant readings
        level_val = None
        actual_level = None
        inflow_val = None
        outflow_val = None
        now = None

        sensor_ids = []
        for r in readings:
            if r["sensor_type"] == "level":
                level_val = r["value"]
                actual_level = r.get("actual_value")
                sensor_ids.append(r["sensor_id"])
                now = r["timestamp"]
            elif r["sensor_type"] == "flow_in":
                inflow_val = r["value"]
                sensor_ids.append(r["sensor_id"])
            elif r["sensor_type"] == "flow_out":
                outflow_val = r["value"]
                sensor_ids.append(r["sensor_id"])

        if level_val is None or inflow_val is None or outflow_val is None or now is None:
            # Not enough data — return neutral state
            return MassBalanceState(
                implied_level=0.0,
                measured_level=0.0,
                discrepancy=0.0,
                implied_delta=0.0,
                measured_delta=0.0,
                flags=[],
            )

        # Initialize on first tick
        if self._window_start_level is None:
            self._window_start_level = level_val
            self._window_start_time = now
            self._implied_level = level_val

        # Trapezoidal integration of net flow
        if self._prev_time is not None:
            dt = now - self._prev_time  # seconds
            if dt > 0:
                # Average net flow over this interval
                prev_net = (self._prev_inflow or 0) - (self._prev_outflow or 0)
                curr_net = inflow_val - outflow_val
                avg_net_flow = (prev_net + curr_net) / 2.0

                # Convert flow (gpm) to level change (ft)
                level_change = avg_net_flow * self.flow_to_level_rate * dt
                self._cumulative_flow_delta += level_change
                self._implied_level += level_change

        # Store for next tick
        self._prev_inflow = inflow_val
        self._prev_outflow = outflow_val
        self._prev_time = now

        # Append to history
        self._history.append((now, inflow_val, outflow_val, level_val))

        # Prune history outside the rolling window
        self._prune_window(now)

        # Compute deltas within the window
        implied_delta = self._cumulative_flow_delta
        measured_delta = level_val - self._window_start_level
        discrepancy = abs(implied_delta - measured_delta)

        # Check for flags
        self.active_flags = self._evaluate_flags(
            discrepancy, implied_delta, measured_delta, sensor_ids, now
        )

        return MassBalanceState(
            implied_level=self._implied_level,
            measured_level=level_val,
            discrepancy=discrepancy,
            implied_delta=implied_delta,
            measured_delta=measured_delta,
            flags=self.active_flags,
            actual_level=actual_level,
        )

    def _prune_window(self, now: float) -> None:
        """Remove entries older than the rolling window and reset the anchor."""
        cutoff = now - self.window_seconds

        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        # Reset window anchor to the oldest remaining entry
        if self._history:
            oldest = self._history[0]
            self._window_start_time = oldest[0]
            self._window_start_level = oldest[3]

            # Recompute cumulative flow delta within window
            self._recompute_flow_delta()

    def _recompute_flow_delta(self) -> None:
        """Recompute cumulative flow delta from the current window history."""
        if len(self._history) < 2:
            self._cumulative_flow_delta = 0.0
            return

        total = 0.0
        entries = list(self._history)
        for i in range(1, len(entries)):
            prev_ts, prev_fi, prev_fo, _ = entries[i - 1]
            curr_ts, curr_fi, curr_fo, _ = entries[i]
            dt = curr_ts - prev_ts
            if dt > 0:
                prev_net = prev_fi - prev_fo
                curr_net = curr_fi - curr_fo
                avg_net = (prev_net + curr_net) / 2.0
                total += avg_net * self.flow_to_level_rate * dt

        self._cumulative_flow_delta = total

    def _evaluate_flags(
        self,
        discrepancy: float,
        implied_delta: float,
        measured_delta: float,
        sensor_ids: list[str],
        now: float,
    ) -> list[MassBalanceFlag]:
        """Evaluate discrepancy against tolerance thresholds."""
        flags = []

        for severity in ("CRITICAL", "WARNING", "INFO"):
            threshold = self.tolerance * SEVERITY_MULTIPLIERS[severity]
            if discrepancy > threshold:
                msg = (
                    f"Mass-balance {severity}: discrepancy of {discrepancy:.1f} ft "
                    f"exceeds {severity} threshold ({threshold:.1f} ft). "
                    f"Flow-implied delta: {implied_delta:+.1f} ft, "
                    f"measured delta: {measured_delta:+.1f} ft."
                )
                flags.append(MassBalanceFlag(
                    severity=severity,
                    discrepancy=discrepancy,
                    implied_delta=implied_delta,
                    measured_delta=measured_delta,
                    sensor_ids=sensor_ids,
                    message=msg,
                    timestamp=now,
                ))
                break  # only report the highest severity

        return flags
