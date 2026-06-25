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
    namur_state: str = "NORMAL"
    evidence: list[dict] = field(default_factory=list)
    recommended_action: str = "Continue normal monitoring."
    dominant_factor: str = "none"
    # Uncertainty band: how wide the score estimate could be (±pct points).
    # Low sample count or unknown calibration age increases uncertainty.
    # This is NOT a probability — it reflects rubric input data quality.
    score_uncertainty_pct: float = 10.0

    def to_dict(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "confidence_pct": self.confidence_pct,
            "tier": self.tier,
            # Uncertainty band: the true score could reasonably be within
            # ±score_uncertainty_pct of the reported value. Not a probability.
            "score_uncertainty_pct": self.score_uncertainty_pct,
            "score_basis": "trust-rubric — governed heuristic, not a calibrated probability",
            "sub_scores": {
                "calibration": round(self.sub_scores.calibration_score, 3),
                "stability": round(self.sub_scores.stability_score, 3),
                "cross_sensor": round(self.sub_scores.cross_sensor_score, 3),
                "physical_plausibility": round(self.sub_scores.physical_plausibility_score, 3),
            },
            "reasons": self.reasons,
            "namur_state": self.namur_state,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "dominant_factor": self.dominant_factor,
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
        per_sensor_type_calibration_intervals: dict[str, float] | None = None,
        per_sensor_type_confidence_weights: dict[str, "ConfidenceWeights"] | None = None,
    ):
        self.weights = weights or ConfidenceWeights()
        self.calibration_interval_days = calibration_interval_days
        # Per-sensor-type overrides — lookup key is sensor_type (e.g. "level", "pressure").
        # When present, these take precedence over the global defaults.
        self._per_sensor_type_calibration_intervals: dict[str, float] = per_sensor_type_calibration_intervals or {}
        self._per_sensor_type_confidence_weights: dict[str, ConfidenceWeights] = per_sensor_type_confidence_weights or {}

        # Per-sensor calibration age in days (simulated — starts at 0, can be overridden)
        self.calibration_ages: dict[str, float] = {}
        # Per-sensor type mapping (sensor_id → sensor_type) populated during score()
        self._sensor_type_map: dict[str, str] = {}

        # Per-sensor reading history (deque of (timestamp, value) tuples)
        self._history: dict[str, deque] = {}

        # Per-sensor: timestamp of the last reading that was different from current
        self._last_change_time: dict[str, float] = {}
        self._last_change_value: dict[str, float] = {}

        # Tier threshold overrides (Module 5 — Startup Mode)
        # When set, _get_tier uses these thresholds instead of the defaults.
        self._tier_thresholds: dict[str, int] | None = None
        self._adaptive_envelopes: dict[str, dict] = {}

    def set_calibration_age(self, sensor_id: str, days: float) -> None:
        """Set the simulated calibration age for a sensor (days since last cal)."""
        self.calibration_ages[sensor_id] = days

    def set_tier_thresholds(self, thresholds: dict[str, int]) -> None:
        """
        Override tier classification thresholds (for Startup Mode).

        Args:
            thresholds: dict with keys HIGH, MEDIUM, LOW, CRITICAL mapping to
                        minimum percentage for that tier.
                        e.g. {"HIGH": 80, "MEDIUM": 70, "LOW": 20, "CRITICAL": 0}
        """
        self._tier_thresholds = thresholds

    def clear_tier_thresholds(self) -> None:
        """Clear tier overrides — revert to default thresholds."""
        self._tier_thresholds = None

    def set_adaptive_envelopes(self, envelopes: dict[str, dict]) -> None:
        """Set learned physical plausibility envelopes keyed by sensor_id."""
        self._adaptive_envelopes = envelopes or {}

    def _get_tier(self, pct: float) -> str:
        """Classify confidence percentage into a tier, respecting any overrides."""
        if self._tier_thresholds:
            if pct >= self._tier_thresholds.get("HIGH", 80):
                return "HIGH"
            elif pct >= self._tier_thresholds.get("MEDIUM", 50):
                return "MEDIUM"
            elif pct >= self._tier_thresholds.get("LOW", 20):
                return "LOW"
            else:
                return "CRITICAL"
        return _tier_from_pct(pct)

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

            # Track sensor type for per-type calibration interval lookup
            self._sensor_type_map[sid] = stype

            # Update history
            if sid not in self._history:
                self._history[sid] = deque(maxlen=HISTORY_WINDOW)
            self._history[sid].append((ts, value))

            # Compute sub-scores
            reasons = []

            failure_mode = r.get("failure_mode")
            cal_score = self._calibration_score(sid, reasons)
            stab_score = self._stability_score(sid, value, ts, reasons)
            cross_score = self._cross_sensor_score(sid, stype, value, readings_by_type, reasons)
            phys_score = self._physical_plausibility_score(sid, stype, value, reasons)

            # Live simulator injections are explicit training-source evidence.
            # Fold them into the deterministic trust rubric so support views
            # respond immediately while still remaining read-only.
            if failure_mode == "calibration_drift":
                cal_score = min(cal_score, 0.45)
                reasons.append("Calibration: simulator drift injection active.")
            elif failure_mode == "stuck_reading":
                stab_score = min(stab_score, 0.25)
                reasons.append("Stability: simulator stuck-reading injection active.")
            elif failure_mode == "sg_mismatch":
                cross_score = min(cross_score, 0.45)
                phys_score = min(phys_score, 0.7)
                reasons.append("Cross-check: simulator specific-gravity mismatch active.")
            elif failure_mode == "command_state_decoupling":
                cross_score = min(cross_score, 0.35)
                reasons.append("Cross-check: simulator command-state decoupling active.")

            sub = SubScores(
                calibration_score=cal_score,
                stability_score=stab_score,
                cross_sensor_score=cross_score,
                physical_plausibility_score=phys_score,
            )

            # Resolve sensor-type-specific weights (fall back to global default)
            w = self._per_sensor_type_confidence_weights.get(stype, self.weights)
            composite = (
                w.calibration * cal_score
                + w.stability * stab_score
                + w.cross_sensor * cross_score
                + w.physical_plausibility * phys_score
            )
            pct = round(max(0.0, min(100.0, composite * 100)), 1)
            tier = self._get_tier(pct)
            dominant_factor = self._dominant_factor(sub)
            namur_state = self._namur_state(tier, sub, failure_mode)
            evidence = self._build_evidence(
                sensor_id=sid,
                sensor_type=stype,
                value=value,
                unit=r.get("unit", ""),
                failure_mode=failure_mode,
                sub_scores=sub,
                reasons=reasons,
            )
            recommended_action = self._recommended_action(
                dominant_factor, sid, tier, namur_state
            )

            uncertainty = self._score_uncertainty(sid, stype, sub)

            results.append(ConfidenceResult(
                sensor_id=sid,
                confidence_pct=pct,
                tier=tier,
                sub_scores=sub,
                reasons=reasons,
                namur_state=namur_state,
                evidence=evidence,
                recommended_action=recommended_action,
                dominant_factor=dominant_factor,
                score_uncertainty_pct=uncertainty,
            ))

        return results

    # ── Sub-score: Calibration ───────────────────────────────────────────

    def _dominant_factor(self, sub_scores: SubScores) -> str:
        """Return the weakest confidence dimension for operator explanation."""
        factors = {
            "calibration": sub_scores.calibration_score,
            "stability": sub_scores.stability_score,
            "cross_sensor": sub_scores.cross_sensor_score,
            "physical_plausibility": sub_scores.physical_plausibility_score,
        }
        factor, score = min(factors.items(), key=lambda item: item[1])
        return factor if score < 0.95 else "none"

    def _namur_state(self, tier: str, sub_scores: SubScores, failure_mode: Optional[str]) -> str:
        """
        Map ConfidenceOS evidence into NAMUR-style maintenance language.

        This does not replace the confidence tier; it gives operators and
        maintainers the industrial condition vocabulary behind the number.
        """
        if tier == "CRITICAL":
            return "FAILURE"
        if failure_mode == "stuck_reading" or sub_scores.stability_score < 0.5:
            return "FAILURE"
        if sub_scores.physical_plausibility_score <= 0.6 or sub_scores.cross_sensor_score <= 0.6:
            return "OUT_OF_SPECIFICATION"
        if tier in ("LOW", "MEDIUM") or sub_scores.calibration_score < 0.7:
            return "MAINTENANCE_REQUIRED"
        return "NORMAL"

    def _recommended_action(self, dominant_factor: str, sensor_id: str, tier: str, namur_state: str) -> str:
        """Translate the dominant weakness into a deterministic first action."""
        if tier == "HIGH" and namur_state == "NORMAL" and dominant_factor == "none":
            return "Continue normal monitoring."
        actions = {
            "calibration": f"Verify calibration record for {sensor_id}; schedule calibration if status is overdue.",
            "stability": f"Verify {sensor_id} locally or compare against an independent field indication.",
            "cross_sensor": f"Cross-check {sensor_id} against adjacent tags and the mass-balance panel before relying on it.",
            "physical_plausibility": f"Inspect process condition and transmitter range for {sensor_id}; confirm the value is physically possible.",
            "none": f"Review {sensor_id} evidence before using this value as a primary operating reference.",
        }
        return actions.get(dominant_factor, actions["none"])

    def _score_uncertainty(self, sensor_id: str, sensor_type: str, sub: SubScores) -> float:
        """
        Estimate how uncertain the composite trust rubric score is, in ±pct points.

        This is NOT a probability; it captures data-quality limitations:
        - Too few history samples → cross-sensor and stability scores are coarse.
        - Unknown calibration age → calibration score could be over- or under-stated.
        - No independent cross-check available → cross-sensor evidence is absent.

        Typical range: 5 (well-observed sensor, known cal) to 25 (new / uncalibrated).
        """
        uncertainty = 5.0  # minimum baseline

        # Sample count uncertainty: stability and cross-sensor need at least 10+ readings
        history = self._history.get(sensor_id)
        n_samples = len(history) if history else 0
        if n_samples < 5:
            uncertainty += 15.0   # essentially no trend data
        elif n_samples < 15:
            uncertainty += 8.0
        elif n_samples < 30:
            uncertainty += 3.0

        # Calibration age uncertainty: unknown age means cal score assumption unverified
        cal_age = self.calibration_ages.get(sensor_id)
        if cal_age is None:
            uncertainty += 8.0    # assumed 0 days — may be wrong

        # Cross-sensor uncertainty: if no adjacent sensors were available
        if sub.cross_sensor_score >= 0.99:
            # Perfect cross-sensor usually means no cross-check ran (defaulted to 1.0)
            uncertainty += 4.0

        return round(min(uncertainty, 30.0), 1)

    def _evidence_status(self, score: float) -> tuple[str, str]:
        if score >= 0.8:
            return "OK", "INFO"
        if score >= 0.5:
            return "DEGRADED", "WARNING"
        return "BAD", "CRITICAL"

    def _build_evidence(
        self,
        sensor_id: str,
        sensor_type: str,
        value: float,
        unit: str,
        failure_mode: Optional[str],
        sub_scores: SubScores,
        reasons: list[str],
    ) -> list[dict]:
        """Build the evidence stack consumed by the advisory UI."""
        age_days = self.calibration_ages.get(sensor_id, 0.0)
        envelope = self._adaptive_envelopes.get(sensor_id) or OPERATING_ENVELOPES.get(sensor_type)
        envelope_text = None
        if envelope:
            envelope_text = f"{envelope['normal_min']:.0f}-{envelope['normal_max']:.0f} {envelope.get('unit', unit)}"

        # Resolve the effective calibration interval for this sensor's type
        _eff_interval = self._per_sensor_type_calibration_intervals.get(
            sensor_type, self.calibration_interval_days
        )
        rows = [
            {
                "category": "calibration",
                "score": sub_scores.calibration_score,
                "message": (
                    f"Calibration age {age_days:.0f} days against "
                    f"{_eff_interval:.0f}-day interval (sensor type: {sensor_type})."
                ),
                "value": round(age_days, 1),
                "threshold": _eff_interval,
                "sensor_type_interval": _eff_interval,
                "action": f"Verify calibration record for {sensor_id}.",
            },
            {
                "category": "stability",
                "score": sub_scores.stability_score,
                "message": self._reason_for_category(reasons, "Stability") or "Signal movement is consistent with recent history.",
                "value": round(value, 2),
                "threshold": f"stuck>{STUCK_SUSPECT_SECONDS:.0f}s",
                "action": f"Compare {sensor_id} with local indication if stability degrades.",
            },
            {
                "category": "cross_sensor",
                "score": sub_scores.cross_sensor_score,
                "message": self._reason_for_category(reasons, "Cross-check") or "Adjacent sensor relationship is currently plausible.",
                "value": round(value, 2),
                "threshold": "process relationship",
                "action": f"Review adjacent tags for {sensor_id}.",
            },
            {
                "category": "physical_plausibility",
                "score": sub_scores.physical_plausibility_score,
                "message": self._reason_for_category(reasons, "Plausibility") or "Reading is within configured physical envelope.",
                "value": round(value, 2),
                "threshold": envelope_text or "not configured",
                "action": f"Confirm transmitter range and process state for {sensor_id}.",
            },
        ]

        evidence = []
        for row in rows:
            status, severity = self._evidence_status(row.pop("score"))
            evidence.append({
                "status": status,
                "severity": severity,
                **row,
            })

        if failure_mode:
            evidence.append({
                "category": "simulation",
                "status": "DEGRADED",
                "severity": "WARNING",
                "message": f"Simulator failure mode active: {failure_mode}.",
                "value": failure_mode,
                "threshold": "scenario",
                "action": f"Treat {sensor_id} as scenario-affected during replay/demo.",
            })

        return evidence

    def _reason_for_category(self, reasons: list[str], prefix: str) -> Optional[str]:
        for reason in reasons:
            if reason.startswith(prefix):
                return reason
        return None

    def _calibration_score(self, sensor_id: str, reasons: list[str]) -> float:
        """
        Starts at 1.0, decays linearly to 0.0 over the applicable calibration interval.
        Interval is resolved per sensor type (from per_sensor_type_calibration_intervals),
        falling back to the global calibration_interval_days default.

        Example: level sensor at 47 days with 180-day interval → score = 1 - 47/180 = 0.739
        """
        age_days = self.calibration_ages.get(sensor_id, 0.0)
        # Resolve interval: per-sensor-type override → global default
        stype = self._sensor_type_map.get(sensor_id)
        if stype and stype in self._per_sensor_type_calibration_intervals:
            interval = self._per_sensor_type_calibration_intervals[stype]
        else:
            interval = self.calibration_interval_days

        if age_days <= 0:
            return 1.0

        score = max(0.0, 1.0 - (age_days / interval))

        if score < 1.0:
            reasons.append(
                f"Calibration: {age_days:.0f} days elapsed "
                f"(interval: {interval:.0f} days"
                + (f", type: {stype}" if stype else "")
                + ")."
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
        envelope = self._adaptive_envelopes.get(sensor_id) or OPERATING_ENVELOPES.get(sensor_type)
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
