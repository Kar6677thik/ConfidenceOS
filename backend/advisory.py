"""
advisory.py - deterministic decision-support helpers for ConfidenceOS.

This layer turns low-level confidence and mass-balance signals into
operator-facing context and fused incidents. It is intentionally read-only:
it never changes simulator or control state.
"""

import time
from typing import Any

from asset_model import action_contract_decisions, trusted_substitute_tags

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
    inferred_mode: dict | None = None,
) -> dict:
    """Infer the active operating context from live plant state."""
    if inferred_mode:
        return {
            "state": inferred_mode.get("mode", inferred_mode.get("state", "STEADY_STATE")),
            "severity": inferred_mode.get("severity", "INFO"),
            "reasons": inferred_mode.get("reasons", []),
            "priority_sensors": inferred_mode.get("priority_sensors", []),
            "layout_hint": inferred_mode.get("layout_hint", "standard_monitoring"),
            "operator_focus": inferred_mode.get("operator_focus", "Review current inferred mode."),
            "inferred_mode": inferred_mode,
        }

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
    """Fuse related advisory signals into collapsed operator-action incidents."""
    now = time.time()
    incidents = []
    mb_flags = mass_balance.get("flags", []) if mass_balance else []
    stale = [_as_dict(flag) for flag in stale_flags]
    degraded = [c for c in confidence if c.get("tier") in ("MEDIUM", "LOW", "CRITICAL")]
    level_degraded = [
        c for c in degraded
        if c.get("sensor_id", "").startswith("LT") or _reading_type(readings, c.get("sensor_id")) == "level"
    ]
    startup_like = plant_context.get("state") in ("STARTUP", "STARTUP_RAMP", "MANUAL_VERIFICATION_REQUIRED")

    if mb_flags and (level_degraded or startup_like):
        sensors = [c["sensor_id"] for c in level_degraded]
        if not sensors:
            sensors = [
                sid for sid in _sensor_ids_from_flags(mb_flags)
                if sid.startswith("LT") or _reading_type(readings, sid) == "level"
            ]
        severity = _worst_severity(
            [f.get("severity", "INFO") for f in mb_flags] +
            [_severity_from_tier(c.get("tier")) for c in level_degraded] +
            (["WARNING"] if startup_like else [])
        )
        first_action = (
            "Do not use indicated level as the sole reference; verify level by sight glass "
            "or local indication before increasing feed."
        )
        contract = _action_contract(
            kind="inventory_accumulation",
            do_not_use=sensors or ["measured_level_as_sole_reference"],
            first_safe_action=first_action,
            readings=readings,
            extra_substitutes=["manual_level_check", "sight_glass"],
        )
        consumed_alarm_types = _consumed_alarm_types(
            level_degraded=level_degraded,
            mb_flags=mb_flags,
            stale_flags=stale if startup_like else [],
            startup_like=startup_like,
        )
        raw_signals = _raw_signals_for_collapse(level_degraded, mb_flags, stale if startup_like else [])
        raw_signal_count = len(raw_signals) + len(consumed_alarm_types)
        incidents.append({
            "incident_id": f"{plant_id}:level-integrity",
            "title": "Inventory accumulation with unreliable level indication",
            "severity": severity,
            "root_trigger": "inventory_accumulation_unreliable_level",
            "abnormal_situation": "inventory_accumulation",
            "alarm_collapse": {
                "collapsed": True,
                "consumed_alarm_types": consumed_alarm_types,
                "raw_signal_count": raw_signal_count,
                "suppressed_alarm_count": max(0, raw_signal_count - 1),
                "operator_question": "Can the operator trust level before increasing feed?",
                "collapse_reason": "All signals affect the same operating basis.",
                "raw_signals": raw_signals,
            },
            "affected_sensors": list(dict.fromkeys(sensors + _sensor_ids_from_flags(mb_flags))),
            "summary": (
                "ConfidenceOS collapsed level confidence, mass-balance, and operating-mode evidence "
                "into one abnormal situation: inventory may be accumulating while level indication is unreliable."
            ),
            "first_action": first_action,
            "suggested_actions": [
                "Compare LT reading with flow-implied level trend.",
                "Verify inflow and outflow totalizers.",
                "Create or confirm a manual level verification before increasing feed.",
            ],
            "action_contract": contract,
            "blocked_decisions": contract["blocked_decisions"],
            "trust_quarantine": {
                "quarantined_signals": [
                    item.get("sensor_id") for item in level_degraded
                    if item.get("trust_state") == "QUARANTINED"
                ] or sensors,
                "substituted_by": contract.get("trusted_substitutes", []),
                "decision_basis_allowed": False,
            },
            "handover_required": True,
            "evidence_refs": _evidence_refs(level_degraded, ["cross_sensor", "physical_plausibility", "calibration"]),
            "context": plant_context.get("state", "UNKNOWN"),
            "source_flags": _source_flags(mb_flags) + _stale_source_flags(stale if startup_like else []),
            "created_at": now,
        })

    elif level_degraded and mb_flags:
        sensors = [c["sensor_id"] for c in level_degraded]
        severity = _worst_severity(
            [f.get("severity", "INFO") for f in mb_flags] +
            [_severity_from_tier(c.get("tier")) for c in level_degraded]
        )
        first_action = "Do not use indicated level as the sole reference; verify level by sight glass or independent field indication."
        contract = _action_contract(
            kind="level_integrity",
            do_not_use=sensors,
            first_safe_action=first_action,
            readings=readings,
            extra_substitutes=["manual_level_check", "sight_glass"],
        )
        incidents.append({
            "incident_id": f"{plant_id}:level-integrity",
            "title": "Level integrity suspect",
            "severity": severity,
            "root_trigger": "level_confidence_mass_balance",
            "affected_sensors": sensors,
            "summary": "Level confidence is degraded while mass-balance residual is active.",
            "first_action": first_action,
            "suggested_actions": [
                "Compare LT reading with flow-implied level trend.",
                "Verify inflow and outflow totalizers.",
                "Check calibration and transmitter status for affected level instrument.",
            ],
            "action_contract": contract,
            "blocked_decisions": contract["blocked_decisions"],
            "handover_required": True,
            "evidence_refs": _evidence_refs(level_degraded, ["cross_sensor", "physical_plausibility", "calibration"]),
            "context": plant_context.get("state", "UNKNOWN"),
            "source_flags": _source_flags(mb_flags),
            "created_at": now,
        })

    if stale:
        sensors = [f.get("sensor_id") or f.get("sensorId") or f.get("id") for f in stale]
        sensors = [sid for sid in sensors if sid]
        first_action = "Verify each stale tag locally before accepting startup conditions."
        contract = _action_contract(
            kind="manual_verification",
            do_not_use=sensors,
            first_safe_action=first_action,
            readings=readings,
            extra_substitutes=["field_operator_confirmation"],
        )
        incidents.append({
            "incident_id": f"{plant_id}:startup-verification",
            "title": "Startup stale-reading verification",
            "severity": "WARNING",
            "root_trigger": "startup_stale_reading",
            "affected_sensors": sensors,
            "summary": "Startup mode has one or more unchanged readings that require field verification.",
            "first_action": first_action,
            "suggested_actions": [
                "Confirm transmitter is updating at the field device.",
                "Compare against an independent local indicator.",
                "Acknowledge only after manual verification is complete.",
            ],
            "action_contract": contract,
            "blocked_decisions": contract["blocked_decisions"],
            "handover_required": True,
            "evidence_refs": [{"sensor_id": sid, "category": "stability"} for sid in sensors],
            "context": plant_context.get("state", "UNKNOWN"),
            "source_flags": _stale_source_flags(stale),
            "created_at": now,
        })

    fused_sensors = {sid for incident in incidents for sid in incident.get("affected_sensors", [])}
    remaining_degraded = [c for c in degraded if c.get("sensor_id") not in fused_sensors]
    if remaining_degraded:
        worst = _worst_severity([_severity_from_tier(c.get("tier")) for c in remaining_degraded])
        sensors = [c["sensor_id"] for c in remaining_degraded]
        lead = sorted(remaining_degraded, key=lambda c: c.get("confidence_pct", 100))[0]
        first_action = lead.get("recommended_action") or f"Review evidence stack for {lead['sensor_id']}."
        contract = _action_contract(
            kind="instrument_integrity",
            do_not_use=[lead["sensor_id"]] if lead.get("tier") in ("LOW", "CRITICAL") else [],
            first_safe_action=first_action,
            readings=readings,
            extra_substitutes=["adjacent_tag_cross_check", "manual_field_check"],
        )
        incidents.append({
            "incident_id": f"{plant_id}:instrument-confidence",
            "title": "Instrument confidence degraded",
            "severity": worst,
            "root_trigger": "confidence_degradation",
            "affected_sensors": sensors,
            "summary": f"{len(remaining_degraded)} instrument(s) below HIGH confidence; lowest is {lead['sensor_id']} at {lead.get('confidence_pct')}%.",
            "first_action": first_action,
            "suggested_actions": [
                "Open the selected sensor evidence stack.",
                "Confirm whether the degraded sensor is primary for current operation.",
                "Schedule maintenance if degradation persists.",
            ],
            "action_contract": contract,
            "blocked_decisions": contract["blocked_decisions"],
            "handover_required": worst in ("CRITICAL", "WARNING"),
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


def build_timeline_events(
    plant_id: str,
    inferred_mode: dict,
    confidence: list[dict],
    mass_balance: dict,
    incidents: list[dict],
    timestamp: float | None = None,
) -> list[dict]:
    """Build lightweight, additive incident timeline events for the current tick."""
    now = timestamp or time.time()
    events = []
    mode = inferred_mode.get("mode") or inferred_mode.get("state") or "STEADY_STATE"
    if mode != "STEADY_STATE":
        events.append(_event(
            plant_id, "mode_detected", mode, inferred_mode.get("severity", "INFO"),
            f"Operating mode inferred: {mode}.", now,
            {"mode": mode, "rule_id": inferred_mode.get("rule_id"), "reasons": inferred_mode.get("reasons", [])},
        ))

    for item in confidence:
        tier = item.get("tier")
        if tier in ("MEDIUM", "LOW", "CRITICAL"):
            sid = item.get("sensor_id", "UNKNOWN")
            events.append(_event(
                plant_id, "confidence_degraded", sid, _severity_from_tier(tier),
                f"{sid} confidence degraded to {item.get('confidence_pct')}% ({tier}).", now,
                {"sensor_id": sid, "confidence_pct": item.get("confidence_pct"), "tier": tier},
            ))

    for flag in (mass_balance or {}).get("flags", []):
        events.append(_event(
            plant_id, "mass_balance_divergence", flag.get("severity", "WARNING"),
            flag.get("severity", "WARNING"), flag.get("message", "Mass-balance divergence active."), now,
            {
                "discrepancy": flag.get("discrepancy"),
                "sensor_ids": flag.get("sensor_ids", []),
            },
        ))

    for incident in incidents:
        contract = incident.get("action_contract")
        if contract:
            events.append(_event(
                plant_id, "action_contract_created", incident.get("incident_id", incident.get("title", "incident")),
                incident.get("severity", "INFO"), f"Action contract active: {incident.get('title')}.", now,
                {"incident_id": incident.get("incident_id"), "action_contract": contract},
            ))
            for decision in contract.get("blocked_decisions", []):
                events.append(_event(
                    plant_id, "decision_freeze_created", decision, incident.get("severity", "INFO"),
                    f"Decision freeze active: {decision}.", now,
                    {
                        "incident_id": incident.get("incident_id"),
                        "decision": decision,
                        "exit_conditions": contract.get("exit_conditions", []),
                    },
                ))

    return events


def _reading_type(readings: list[dict], sensor_id: str | None) -> str | None:
    for reading in readings:
        if reading.get("sensor_id") == sensor_id:
            return reading.get("sensor_type")
    return None


def _action_contract(
    kind: str,
    do_not_use: list[str],
    first_safe_action: str,
    readings: list[dict],
    extra_substitutes: list[str] | None = None,
) -> dict:
    substitutes = _trusted_substitutes(readings)
    for item in extra_substitutes or []:
        substitutes.append(item)
    if kind in ("inventory_accumulation", "level_integrity"):
        substitutes.append("flow_implied_level_from_FI_2010_FO_2020")
        blocked = action_contract_decisions() or [
            "increase_feed",
            "increase_load",
            "accept_handover_without_verification",
        ]
        exits = ["affected level confidence restored above 80%", "manual level verification token active"]
    elif kind == "manual_verification":
        blocked = ["accept_startup_conditions", "accept_handover_without_verification"]
        exits = ["field verification completed", "stale reading clears"]
    else:
        blocked = ["use_degraded_signal_as_primary_reference"]
        exits = ["affected sensor confidence restored above 80%", "independent verification completed"]

    return {
        "do_not_use": list(dict.fromkeys(do_not_use)),
        "trusted_substitutes": list(dict.fromkeys(substitutes)),
        "first_safe_action": first_safe_action,
        "operator_single_safe_move": (
            "Verify level locally before increasing feed."
            if kind in ("inventory_accumulation", "level_integrity")
            else first_safe_action
        ),
        "blocked_decisions": blocked,
        "blocked_basis": list(dict.fromkeys(do_not_use)),
        "exit_conditions": exits,
    }


def _trusted_substitutes(readings: list[dict]) -> list[str]:
    substitutes = trusted_substitute_tags(readings)
    for reading in readings:
        sid = reading.get("sensor_id")
        stype = reading.get("sensor_type")
        if sid and stype in ("flow_in", "flow_out", "pressure"):
            substitutes.append(sid)
    return substitutes


def _sensor_ids_from_flags(flags: list[dict]) -> list[str]:
    sensors = []
    for flag in flags:
        sid = flag.get("sensor_id") or flag.get("sensorId") or flag.get("id")
        if sid:
            sensors.append(sid)
        for nested in flag.get("sensor_ids", []) or []:
            sensors.append(nested)
    return list(dict.fromkeys(sensors))


def _consumed_alarm_types(
    level_degraded: list[dict],
    mb_flags: list[dict],
    stale_flags: list[dict],
    startup_like: bool,
) -> list[str]:
    consumed = []
    if level_degraded:
        consumed.append("confidence_degraded")
    if mb_flags:
        consumed.append("mass_balance_divergence")
    if startup_like:
        consumed.append("mode_detected")
    if stale_flags:
        consumed.append("stale_reading")
    return consumed


def _stale_source_flags(stale: list[dict]) -> list[dict]:
    return [
        {
            "source": f.get("sensor_id") or f.get("sensorId") or f.get("id"),
            "severity": "WARNING",
            "message": f"Reading unchanged for {f.get('duration_seconds', 0):.0f}s.",
        }
        for f in stale
    ]


def _event(
    plant_id: str,
    event_type: str,
    subject: str,
    severity: str,
    message: str,
    timestamp: float,
    details: dict,
) -> dict:
    return {
        "event_id": f"{plant_id}:{event_type}:{subject}",
        "plant_id": plant_id,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "timestamp": timestamp,
        "details": details,
    }


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


def _raw_signals_for_collapse(level_degraded: list[dict], mb_flags: list[dict], stale_flags: list[dict]) -> list[str]:
    signals = [item.get("sensor_id") for item in level_degraded if item.get("sensor_id")]
    signals.extend(_sensor_ids_from_flags(mb_flags))
    signals.extend(
        flag.get("sensor_id") or flag.get("sensorId") or flag.get("id")
        for flag in stale_flags
        if flag.get("sensor_id") or flag.get("sensorId") or flag.get("id")
    )
    return list(dict.fromkeys(signals))
