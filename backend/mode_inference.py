"""
mode_inference.py - deterministic operating-mode inference for ConfidenceOS.

The engine is deliberately rule-based. It reads the live tag stream and
advisory evidence, keeps a short local history, and returns a frontend-friendly
mode payload without writing to control state.
"""

from collections import deque
from typing import Any


MODE_SEVERITY = {
    "STEADY_STATE": "INFO",
    "STARTUP_RAMP": "WARNING",
    "MASS_BALANCE_DIVERGENCE": "WARNING",
    "INSTRUMENTATION_SUSPECT": "WARNING",
    "MANUAL_VERIFICATION_REQUIRED": "CRITICAL",
}


class ModeInferenceEngine:
    """Infer plant operating mode from deterministic process rules."""

    def __init__(self, history_size: int = 60):
        self.history_size = history_size
        self._history: dict[str, deque] = {}
        self._last_mode = "STEADY_STATE"

    def infer(
        self,
        readings: list[dict],
        confidence: list[dict],
        mass_balance: dict | None,
        startup_mode: dict | None,
        stale_flags: list[Any] | None,
    ) -> dict:
        """Return the current inferred operating mode and rule evidence."""
        self._record_readings(readings)

        stale = [_as_dict(flag) for flag in (stale_flags or [])]
        degraded = [
            item for item in confidence
            if item.get("tier") in ("MEDIUM", "LOW", "CRITICAL")
        ]
        critical = [
            item for item in confidence
            if item.get("tier") in ("LOW", "CRITICAL")
        ]
        mb_flags = (mass_balance or {}).get("flags", [])
        mb_active = any(flag.get("severity") in ("WARNING", "CRITICAL") for flag in mb_flags)
        manual_startup = bool((startup_mode or {}).get("is_active"))
        ramp_evidence = self._startup_ramp_evidence(readings)

        mode = "STEADY_STATE"
        rule_id = "steady_state_nominal"
        reasons = ["No abnormal operating mode inferred from current process evidence."]
        priority_sensors: list[str] = []

        if stale:
            mode = "MANUAL_VERIFICATION_REQUIRED"
            rule_id = "stale_sensor_requires_field_check"
            priority_sensors = _sensor_ids_from_flags(stale)
            reasons = [
                "One or more startup readings are stale and require manual verification.",
            ]
        elif mb_active:
            mode = "MASS_BALANCE_DIVERGENCE"
            rule_id = "flow_implied_level_disagrees_with_measured_level"
            priority_sensors = _sensor_ids_from_flags(mb_flags)
            reasons = ["Measured level and flow-implied level are outside tolerance."]
            if manual_startup or ramp_evidence:
                reasons.append("Startup or ramping evidence is also active, increasing verification priority.")
        elif critical:
            mode = "MANUAL_VERIFICATION_REQUIRED"
            rule_id = "low_confidence_primary_reference"
            priority_sensors = _sensor_ids_from_confidence(critical)
            reasons = ["A LOW or CRITICAL confidence instrument requires field verification before use."]
        elif manual_startup or ramp_evidence:
            mode = "STARTUP_RAMP"
            rule_id = "startup_or_ramp_detected"
            reasons = ["Startup transition inferred from manual startup state or live ramp evidence."]
        elif degraded:
            mode = "INSTRUMENTATION_SUSPECT"
            rule_id = "confidence_degradation_detected"
            priority_sensors = _sensor_ids_from_confidence(degraded)
            reasons = ["One or more instruments have degraded confidence."]

        evidence = {
            "manual_startup_active": manual_startup,
            "startup_ramp_detected": bool(ramp_evidence),
            "ramp_evidence": ramp_evidence,
            "mass_balance_flag_count": len(mb_flags),
            "degraded_sensor_count": len(degraded),
            "critical_sensor_count": len(critical),
            "stale_flag_count": len(stale),
        }

        previous = self._last_mode
        self._last_mode = mode

        return {
            "mode": mode,
            "state": mode,
            "severity": MODE_SEVERITY[mode],
            "rule_id": rule_id,
            "reasons": reasons,
            "priority_sensors": list(dict.fromkeys(priority_sensors))[:6],
            "layout_hint": _layout_hint(mode),
            "operator_focus": _operator_focus(mode),
            "evidence": evidence,
            "previous_mode": previous,
            "changed": previous != mode,
        }

    def _record_readings(self, readings: list[dict]) -> None:
        for reading in readings:
            sid = reading.get("sensor_id")
            if not sid:
                continue
            if sid not in self._history:
                self._history[sid] = deque(maxlen=self.history_size)
            self._history[sid].append((
                float(reading.get("timestamp") or 0),
                float(reading.get("value") or 0),
                reading.get("sensor_type"),
            ))

    def _startup_ramp_evidence(self, readings: list[dict]) -> list[dict]:
        evidence = []
        by_type = {reading.get("sensor_type"): reading for reading in readings}

        inflow = by_type.get("flow_in")
        if inflow and self._delta_for_sensor(inflow.get("sensor_id")) > 8.0:
            evidence.append({
                "signal": inflow.get("sensor_id"),
                "rule": "inflow_ramp_rate",
                "message": "Inflow has increased materially over the recent window.",
            })

        temperature = by_type.get("temperature")
        if temperature and abs(self._delta_for_sensor(temperature.get("sensor_id"))) > 5.0:
            evidence.append({
                "signal": temperature.get("sensor_id"),
                "rule": "temperature_transition",
                "message": "Temperature is moving enough to indicate process transition.",
            })

        valve = by_type.get("valve")
        if valve and abs(self._delta_for_sensor(valve.get("sensor_id"))) > 15.0:
            evidence.append({
                "signal": valve.get("sensor_id"),
                "rule": "valve_transition",
                "message": "Valve position is changing over the recent window.",
            })

        return evidence

    def _delta_for_sensor(self, sensor_id: str | None) -> float:
        if not sensor_id:
            return 0.0
        history = self._history.get(sensor_id)
        if not history or len(history) < 6:
            return 0.0
        return history[-1][1] - history[0][1]


def _as_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return {}


def _sensor_ids_from_flags(flags: list[dict]) -> list[str]:
    sensors: list[str] = []
    for flag in flags:
        sid = flag.get("sensor_id") or flag.get("sensorId") or flag.get("id")
        if sid:
            sensors.append(sid)
        for nested in flag.get("sensor_ids", []) or []:
            sensors.append(nested)
    return sensors


def _sensor_ids_from_confidence(confidence: list[dict]) -> list[str]:
    return [item.get("sensor_id") for item in confidence if item.get("sensor_id")]


def _layout_hint(mode: str) -> str:
    return {
        "STEADY_STATE": "standard_monitoring",
        "STARTUP_RAMP": "startup_verification",
        "MASS_BALANCE_DIVERGENCE": "promote_mass_balance",
        "INSTRUMENTATION_SUSPECT": "promote_evidence",
        "MANUAL_VERIFICATION_REQUIRED": "verification_required",
    }[mode]


def _operator_focus(mode: str) -> str:
    return {
        "STEADY_STATE": "All primary instruments are within advisory limits.",
        "STARTUP_RAMP": "Startup transition detected: verify stale readings and mass-balance before increasing load.",
        "MASS_BALANCE_DIVERGENCE": "Mass-balance divergence active: verify level and flow references before acting.",
        "INSTRUMENTATION_SUSPECT": "Instrument trust is degraded: use evidence stack and independent verification.",
        "MANUAL_VERIFICATION_REQUIRED": "Manual verification is required before relying on affected readings or blocked decisions.",
    }[mode]
