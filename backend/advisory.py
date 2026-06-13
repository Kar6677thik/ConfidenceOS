"""
advisory.py - deterministic decision-support helpers for ConfidenceOS.

This layer turns low-level confidence and mass-balance signals into
operator-facing context and fused incidents. It is intentionally read-only:
it never changes simulator or control state.
"""

import time
from typing import Any


SEVERITY_RANK = {"CRITICAL": 0, "WARNING": 1, "LOW": 1, "MEDIUM": 2, "INFO": 3}


def _as_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return {}


def _severity_from_tier(tier: str | None) -> str:
    if tier == "CRITICAL":
        return "CRITICAL"
    if tier == "LOW":
        return "WARNING"
    if tier == "MEDIUM":
        return "MEDIUM"
    return "INFO"


def _worst_severity(values: list[str]) -> str:
    if not values:
        return "INFO"
    return sorted(values, key=lambda sev: SEVERITY_RANK.get(sev, 99))[0]


def detect_plant_context(
    readings: list[dict],
    confidence: list[dict],
    mass_balance: dict,
    mode: dict,
    stale_flags: list[Any],
) -> dict:
    """Infer the active operating context from live plant state."""
    mb_flags = mass_balance.get("flags", []) if mass_balance else []
    degraded = [c for c in confidence if c.get("tier") in ("MEDIUM", "LOW", "CRITICAL")]
    level_degraded = [
        c for c in degraded
        if c.get("sensor_id", "").startswith("LT") or _reading_type(readings, c.get("sensor_id")) == "level"
    ]
    stale = [_as_dict(flag) for flag in stale_flags]

    reasons = []
    priority_sensors = []
    severity = "INFO"
    state = "STEADY_STATE"
    layout_hint = "standard_monitoring"
    operator_focus = "All primary instruments are within advisory limits."

    if mode.get("is_active"):
        state = "STARTUP"
        severity = "WARNING"
        layout_hint = "startup_verification"
        operator_focus = "Startup mode active: verify stale readings and mass-balance before handover."
        reasons.append("Startup mode applies stricter confidence and mass-balance scrutiny.")
    elif any(f.get("severity") in ("WARNING", "CRITICAL") for f in mb_flags):
        state = "MASS_BALANCE_DIVERGENCE"
        severity = _worst_severity([f.get("severity", "INFO") for f in mb_flags])
        layout_hint = "promote_mass_balance"
        operator_focus = "Mass-balance divergence active: verify level and flow references before acting."
        reasons.append("Measured level and flow-implied level are outside tolerance.")
    elif level_degraded or len(degraded) >= 2 or stale:
        state = "INSTRUMENTATION_SUSPECT"
        severity = _worst_severity([_severity_from_tier(c.get("tier")) for c in degraded] + (["WARNING"] if stale else []))
        layout_hint = "promote_evidence"
        operator_focus = "Instrument trust is degraded: use evidence stack and independent verification."
        reasons.append("One or more instruments have degraded confidence or stale readings.")
    else:
        reasons.append("No fused advisory condition is active.")

    for item in degraded:
        sid = item.get("sensor_id")
        if sid:
            priority_sensors.append(sid)
    for flag in stale:
        sid = flag.get("sensor_id") or flag.get("sensorId") or flag.get("id")
        if sid:
            priority_sensors.append(sid)

    return {
        "state": state,
        "severity": severity,
        "reasons": reasons,
        "priority_sensors": list(dict.fromkeys(priority_sensors))[:5],
        "layout_hint": layout_hint,
        "operator_focus": operator_focus,
    }


def build_incidents(
    plant_id: str,
    readings: list[dict],
    confidence: list[dict],
    mass_balance: dict,
    stale_flags: list[Any],
    plant_context: dict,
) -> list[dict]:
    """Fuse related advisory signals into operator-action incidents."""
    now = time.time()
    incidents = []
    mb_flags = mass_balance.get("flags", []) if mass_balance else []
    stale = [_as_dict(flag) for flag in stale_flags]
    degraded = [c for c in confidence if c.get("tier") in ("MEDIUM", "LOW", "CRITICAL")]
    level_degraded = [
        c for c in degraded
        if c.get("sensor_id", "").startswith("LT") or _reading_type(readings, c.get("sensor_id")) == "level"
    ]

    if level_degraded and mb_flags:
        sensors = [c["sensor_id"] for c in level_degraded]
        severity = _worst_severity(
            [f.get("severity", "INFO") for f in mb_flags] +
            [_severity_from_tier(c.get("tier")) for c in level_degraded]
        )
        incidents.append({
            "incident_id": f"{plant_id}:level-integrity",
            "title": "Level integrity suspect",
            "severity": severity,
            "root_trigger": "level_confidence_mass_balance",
            "affected_sensors": sensors,
            "summary": "Level confidence is degraded while mass-balance residual is active.",
            "first_action": "Do not use indicated level as the sole reference; verify level by sight glass or independent field indication.",
            "suggested_actions": [
                "Compare LT reading with flow-implied level trend.",
                "Verify inflow and outflow totalizers.",
                "Check calibration and transmitter status for affected level instrument.",
            ],
            "evidence_refs": _evidence_refs(level_degraded, ["cross_sensor", "physical_plausibility", "calibration"]),
            "context": plant_context.get("state", "UNKNOWN"),
            "source_flags": _source_flags(mb_flags),
            "created_at": now,
        })

    if stale:
        sensors = [f.get("sensor_id") or f.get("sensorId") or f.get("id") for f in stale]
        sensors = [sid for sid in sensors if sid]
        incidents.append({
            "incident_id": f"{plant_id}:startup-verification",
            "title": "Startup stale-reading verification",
            "severity": "WARNING",
            "root_trigger": "startup_stale_reading",
            "affected_sensors": sensors,
            "summary": "Startup mode has one or more unchanged readings that require field verification.",
            "first_action": "Verify each stale tag locally before accepting startup conditions.",
            "suggested_actions": [
                "Confirm transmitter is updating at the field device.",
                "Compare against an independent local indicator.",
                "Acknowledge only after manual verification is complete.",
            ],
            "evidence_refs": [{"sensor_id": sid, "category": "stability"} for sid in sensors],
            "context": plant_context.get("state", "UNKNOWN"),
            "source_flags": [
                {
                    "source": f.get("sensor_id") or f.get("sensorId") or f.get("id"),
                    "severity": "WARNING",
                    "message": f"Reading unchanged for {f.get('duration_seconds', 0):.0f}s.",
                }
                for f in stale
            ],
            "created_at": now,
        })

    fused_sensors = {sid for incident in incidents for sid in incident.get("affected_sensors", [])}
    remaining_degraded = [c for c in degraded if c.get("sensor_id") not in fused_sensors]
    if remaining_degraded:
        worst = _worst_severity([_severity_from_tier(c.get("tier")) for c in remaining_degraded])
        sensors = [c["sensor_id"] for c in remaining_degraded]
        lead = sorted(remaining_degraded, key=lambda c: c.get("confidence_pct", 100))[0]
        incidents.append({
            "incident_id": f"{plant_id}:instrument-confidence",
            "title": "Instrument confidence degraded",
            "severity": worst,
            "root_trigger": "confidence_degradation",
            "affected_sensors": sensors,
            "summary": f"{len(remaining_degraded)} instrument(s) below HIGH confidence; lowest is {lead['sensor_id']} at {lead.get('confidence_pct')}%.",
            "first_action": lead.get("recommended_action") or f"Review evidence stack for {lead['sensor_id']}.",
            "suggested_actions": [
                "Open the selected sensor evidence stack.",
                "Confirm whether the degraded sensor is primary for current operation.",
                "Schedule maintenance if degradation persists.",
            ],
            "evidence_refs": _evidence_refs(remaining_degraded, ["calibration", "stability", "cross_sensor", "physical_plausibility"]),
            "context": plant_context.get("state", "UNKNOWN"),
            "source_flags": [
                {
                    "source": c.get("sensor_id"),
                    "severity": _severity_from_tier(c.get("tier")),
                    "message": c.get("reasons", [f"Confidence {c.get('confidence_pct')}%"])[0],
                }
                for c in remaining_degraded
            ],
            "created_at": now,
        })

    return sorted(incidents, key=lambda item: SEVERITY_RANK.get(item.get("severity"), 99))


def _reading_type(readings: list[dict], sensor_id: str | None) -> str | None:
    for reading in readings:
        if reading.get("sensor_id") == sensor_id:
            return reading.get("sensor_type")
    return None


def _evidence_refs(confidence_items: list[dict], categories: list[str]) -> list[dict]:
    refs = []
    for item in confidence_items:
        sid = item.get("sensor_id")
        for evidence in item.get("evidence", []):
            if evidence.get("category") in categories and evidence.get("status") != "OK":
                refs.append({
                    "sensor_id": sid,
                    "category": evidence.get("category"),
                    "severity": evidence.get("severity"),
                    "message": evidence.get("message"),
                })
    return refs[:8]


def _source_flags(flags: list[dict]) -> list[dict]:
    return [
        {
            "source": flag.get("source") or flag.get("sensor_id") or "MASS-BAL",
            "severity": flag.get("severity", "INFO"),
            "message": flag.get("message", ""),
        }
        for flag in flags
    ]
