"""
confidence.py — Confidence Scoring Engine for ConfidenceOS (Module 2).

Produces a 0-100% composite trust score for each sensor reading in real time.

Formula:
    confidence(sensor) = w1 * calibration_score
                       + w2 * stability_score
                       + w3 * cross_sensor_score
                       + w4 * physical_plausibility_score

Default weights: [0.30, 0.20, 0.30, 0.20]

Output tiers:
    HIGH     (80-100%)  — green, reliable
    MEDIUM   (50-79%)   — amber, degraded
    LOW      (20-49%)   — orange, do not trust without cross-verification
    CRITICAL (0-19%)    — red, likely wrong
"""

from dataclasses import dataclass, field
from typing import Optional
from collections import deque
import time


# ─── Configuration ───────────────────────────────────────────────────────────

@dataclass
class ConfidenceWeights:
    """Weights for the composite confidence score. Must sum to 1.0."""
    calibration: float = 0.30
    stability: float = 0.20
    cross_sensor: float = 0.30
    physical_plausibility: float = 0.20


# Per-sensor-type operating envelopes for physical plausibility
OPERATING_ENVELOPES = {
    "level":       {"normal_min": 5.0,   "normal_max": 150.0, "unit": "ft"},
    "flow_in":     {"normal_min": 10.0,  "normal_max": 400.0, "unit": "gpm"},
    "flow_out":    {"normal_min": 10.0,  "normal_max": 400.0, "unit": "gpm"},
    "pressure":    {"normal_min": 5.0,   "normal_max": 60.0,  "unit": "psi"},
    "temperature": {"normal_min": 100.0, "normal_max": 600.0, "unit": "F"},
    "valve":       {"normal_min": 0.0,   "normal_max": 100.0, "unit": "%"},
}

# Default calibration interval in days
DEFAULT_CALIBRATION_INTERVAL_DAYS = 90.0

# How many seconds of unchanging reading before stability degrades
STUCK_SUSPECT_SECONDS = 30.0

# History window size (number of readings to keep per sensor for stability calc)
HISTORY_WINDOW = 60


# ─── Data types ──────────────────────────────────────────────────────────────

@dataclass
class SubScores:
    calibration_score: float
    stability_score: float
    cross_sensor_score: float
    physical_plausibility_score: float


@dataclass
class ConfidenceResult:
    """Full confidence assessment for a single sensor reading."""
    sensor_id: str
    confidence_pct: float          # 0-100
    tier: str                      # HIGH, MEDIUM, LOW, CRITICAL
    sub_scores: SubScores
    reasons: list[str]             # Human-readable reason strings

    def to_dict(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "confidence_pct": self.confidence_pct,
            "tier": self.tier,
            "sub_scores": {
                "calibration": round(self.sub_scores.calibration_score, 3),
                "stability": round(self.sub_scores.stability_score, 3),
                "cross_sensor": round(self.sub_scores.cross_sensor_score, 3),
                "physical_plausibility": round(self.sub_scores.physical_plausibility_score, 3),
            },
            "reasons": self.reasons,
        }


def _tier_from_pct(pct: float) -> str:
    if pct >= 80:
        return "HIGH"
    elif pct >= 50:
        return "MEDIUM"
    elif pct >= 20:
        return "LOW"
    else:
        return "CRITICAL"


# ─── Confidence Scoring Engine ───────────────────────────────────────────────

class ConfidenceEngine:
    """
    Stateful engine that computes confidence scores for sensor readings.

    Maintains per-sensor history for stability analysis and cross-sensor
    consistency checks. Call score_readings() once per tick with all
    current sensor readings.

    Usage:
        engine = ConfidenceEngine()
        results = engine.score_readings(readings)
    """

    def __init__(
        self,
        weights: ConfidenceWeights | None = None,
        calibration_interval_days: float = DEFAULT_CALIBRATION_INTERVAL_DAYS,
    ):
        self.weights = weights or ConfidenceWeights()
        self.calibration_interval_days = calibration_interval_days

        # Per-sensor calibration age in days (simulated — starts at 0, can be overridden)
        self.calibration_ages: dict[str, float] = {}

        # Per-sensor reading history (deque of (timestamp, value) tuples)
        self._history: dict[str, deque] = {}

        # Per-sensor: timestamp of the last reading that was different from current
        self._last_change_time: dict[str, float] = {}
        self._last_change_value: dict[str, float] = {}

    def set_calibration_age(self, sensor_id: str, days: float) -> None:
        """Set the simulated calibration age for a sensor (days since last cal)."""
        self.calibration_ages[sensor_id] = days

    def score_readings(self, readings: list[dict]) -> list[ConfidenceResult]:
        """
        Score all sensor readings from a single tick.

        Args:
            readings: list of reading dicts from SensorSimulator.tick()
                      Each has: sensor_id, sensor_type, value, unit, timestamp, failure_mode

        Returns:
            List of ConfidenceResult for each reading.
        """
        # Build a lookup for cross-sensor checks
        readings_by_type = {}
        readings_by_id = {}
        for r in readings:
            readings_by_type[r["sensor_type"]] = r
            readings_by_id[r["sensor_id"]] = r

        results = []
        for r in readings:
            sid = r["sensor_id"]
            stype = r["sensor_type"]
            value = r["value"]
            ts = r["timestamp"]

            # Update history
            if sid not in self._history:
                self._history[sid] = deque(maxlen=HISTORY_WINDOW)
            self._history[sid].append((ts, value))

            # Compute sub-scores
            reasons = []

            cal_score = self._calibration_score(sid, reasons)
            stab_score = self._stability_score(sid, value, ts, reasons)
            cross_score = self._cross_sensor_score(sid, stype, value, readings_by_type, reasons)
            phys_score = self._physical_plausibility_score(sid, stype, value, reasons)

            sub = SubScores(
                calibration_score=cal_score,
                stability_score=stab_score,
                cross_sensor_score=cross_score,
                physical_plausibility_score=phys_score,
            )

            w = self.weights
            composite = (
                w.calibration * cal_score
                + w.stability * stab_score
                + w.cross_sensor * cross_score
                + w.physical_plausibility * phys_score
            )
            pct = round(max(0.0, min(100.0, composite * 100)), 1)
            tier = _tier_from_pct(pct)

            results.append(ConfidenceResult(
                sensor_id=sid,
                confidence_pct=pct,
                tier=tier,
                sub_scores=sub,
                reasons=reasons,
            ))

        return results

    # ── Sub-score: Calibration ───────────────────────────────────────────

    def _calibration_score(self, sensor_id: str, reasons: list[str]) -> float:
        """
        Starts at 1.0, decays linearly to 0.0 over calibration_interval_days.
        At 47 days with 90-day interval: score = 1 - 47/90 = 0.478
        """
        age_days = self.calibration_ages.get(sensor_id, 0.0)
        interval = self.calibration_interval_days

        if age_days <= 0:
            return 1.0

        score = max(0.0, 1.0 - (age_days / interval))

        if score < 1.0:
            reasons.append(
                f"Calibration: {age_days:.0f} days elapsed (interval: {interval:.0f} days)."
            )

        return score

    # ── Sub-score: Stability ─────────────────────────────────────────────

    def _stability_score(
        self, sensor_id: str, value: float, ts: float, reasons: list[str]
    ) -> float:
        """
        1.0 if reading variance is within historical norm.
        Decays if reading is unchanging for a suspicious duration (stuck sensor)
        or shows unusual step changes.
        """
        score = 1.0
        history = self._history.get(sensor_id, deque())

        if len(history) < 3:
            return 1.0  # not enough data yet

        # --- Stuck detection ---
        prev_val = self._last_change_value.get(sensor_id)
        prev_time = self._last_change_time.get(sensor_id)

        # Consider "changed" if value differs by more than a tiny epsilon
        if prev_val is None or abs(value - prev_val) > 0.001:
            self._last_change_value[sensor_id] = value
            self._last_change_time[sensor_id] = ts
        else:
            # Value hasn't changed — how long?
            if prev_time is not None:
                stuck_duration = ts - prev_time
                if stuck_duration > STUCK_SUSPECT_SECONDS:
                    # Linearly decay from 1.0 to 0.0 over 5x the suspect threshold
                    decay = stuck_duration / (STUCK_SUSPECT_SECONDS * 5)
                    score = max(0.0, 1.0 - decay)
                    reasons.append(
                        f"Stability: reading unchanged for {stuck_duration:.0f}s (suspect > {STUCK_SUSPECT_SECONDS:.0f}s)."
                    )
                    return score

        # --- Step change detection ---
        values = [v for _, v in history]
        if len(values) >= 5:
            recent_avg = sum(values[-5:]) / 5
            older_avg = sum(values[:-5]) / max(1, len(values) - 5)
            if older_avg != 0:
                step_pct = abs(recent_avg - older_avg) / abs(older_avg)
                if step_pct > 0.15:  # >15% sudden shift
                    score = max(0.2, 1.0 - step_pct)
                    reasons.append(
                        f"Stability: step change detected ({step_pct*100:.1f}% shift)."
                    )

        return score

    # ── Sub-score: Cross-sensor consistency ──────────────────────────────

    def _cross_sensor_score(
        self,
        sensor_id: str,
        sensor_type: str,
        value: float,
        readings_by_type: dict,
        reasons: list[str],
    ) -> float:
        """
        1.0 if sensor reading is consistent with adjacent sensors under
        known physical relationships. Key relationship: level should be
        consistent with integrated flow delta.
        """
        # Level vs. flow cross-check
        if sensor_type == "level":
            return self._cross_check_level_vs_flow(sensor_id, value, readings_by_type, reasons)

        # Flow sensors: check that inflow and outflow are in plausible ratio
        if sensor_type in ("flow_in", "flow_out"):
            return self._cross_check_flows(sensor_id, sensor_type, value, readings_by_type, reasons)

        # Pressure: should correlate with level (more level = more pressure)
        if sensor_type == "pressure":
            return self._cross_check_pressure_vs_level(sensor_id, value, readings_by_type, reasons)

        # Valve and temperature: no strong cross-check implemented yet
        return 1.0

    def _cross_check_level_vs_flow(
        self, sensor_id: str, level_value: float,
        readings_by_type: dict, reasons: list[str],
    ) -> float:
        """Check level sensor against flow-implied level trend."""
        fi = readings_by_type.get("flow_in")
        fo = readings_by_type.get("flow_out")

        if fi is None or fo is None:
            return 1.0

        # If inflow >> outflow, level should be rising. If level is flat or dropping, flag.
        net_flow = fi["value"] - fo["value"]  # gpm
        level_history = self._history.get(sensor_id, deque())

        if len(level_history) < 10:
            return 1.0

        # Level trend over last 10 readings
        old_level = level_history[-10][1]
        level_delta = level_value - old_level

        # If net flow is positive (filling), level should rise.
        # If they disagree significantly, flag.
        # Convert flow to expected level change (rough heuristic — 1 gpm ≈ 0.01 ft/s)
        expected_delta_sign = 1 if net_flow > 5 else (-1 if net_flow < -5 else 0)
        actual_delta_sign = 1 if level_delta > 1 else (-1 if level_delta < -1 else 0)

        if expected_delta_sign != 0 and actual_delta_sign != 0 and expected_delta_sign != actual_delta_sign:
            # Strong disagreement
            reasons.append(
                f"Cross-check: level trend ({level_delta:+.1f} ft) inconsistent "
                f"with net flow ({net_flow:+.1f} gpm)."
            )
            return 0.3

        # Magnitude check: large net flow but flat level
        if abs(net_flow) > 20 and abs(level_delta) < 0.5:
            divergence = abs(net_flow) / 20.0  # normalized
            score = max(0.2, 1.0 - divergence * 0.3)
            if score < 0.9:
                reasons.append(
                    f"Cross-check: net flow {net_flow:+.1f} gpm but level nearly flat "
                    f"(delta {level_delta:+.1f} ft)."
                )
            return score

        return 1.0

    def _cross_check_flows(
        self, sensor_id: str, sensor_type: str, value: float,
        readings_by_type: dict, reasons: list[str],
    ) -> float:
        """Check that inflow and outflow are in a plausible ratio."""
        fi = readings_by_type.get("flow_in")
        fo = readings_by_type.get("flow_out")

        if fi is None or fo is None:
            return 1.0

        ratio = fi["value"] / max(fo["value"], 0.01)
        # In normal operation, ratio should be roughly 0.5 to 2.0
        if ratio > 3.0 or ratio < 0.33:
            reasons.append(
                f"Cross-check: inflow/outflow ratio {ratio:.2f} outside normal range."
            )
            return max(0.1, 1.0 - abs(ratio - 1.0) * 0.3)

        return 1.0

    def _cross_check_pressure_vs_level(
        self, sensor_id: str, pressure: float,
        readings_by_type: dict, reasons: list[str],
    ) -> float:
        """Pressure should loosely correlate with level."""
        lt = readings_by_type.get("level")
        if lt is None:
            return 1.0

        # Very basic: if level is very high but pressure is very low, flag
        level_pct = lt["value"] / 200.0  # fraction of max
        pressure_pct = pressure / 100.0   # fraction of max

        if level_pct > 0.5 and pressure_pct < 0.1:
            reasons.append(
                f"Cross-check: level at {lt['value']:.0f} ft but pressure only {pressure:.1f} psi."
            )
            return 0.4

        return 1.0

    # ── Sub-score: Physical plausibility ─────────────────────────────────

    def _physical_plausibility_score(
        self, sensor_id: str, sensor_type: str, value: float, reasons: list[str],
    ) -> float:
        """
        1.0 if within normal operating envelope.
        0.0 if reading is impossible given physical constraints.
        """
        envelope = OPERATING_ENVELOPES.get(sensor_type)
        if envelope is None:
            return 1.0

        nmin = envelope["normal_min"]
        nmax = envelope["normal_max"]

        if nmin <= value <= nmax:
            return 1.0

        # How far outside the envelope?
        if value < nmin:
            deviation = (nmin - value) / max(nmin, 1.0)
        else:
            deviation = (value - nmax) / max(nmax, 1.0)

        score = max(0.0, 1.0 - deviation * 2.0)

        reasons.append(
            f"Plausibility: reading {value:.1f} outside normal envelope "
            f"[{nmin:.0f}-{nmax:.0f}]."
        )

        return score
