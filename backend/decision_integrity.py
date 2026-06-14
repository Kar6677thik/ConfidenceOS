"""
decision_integrity.py - Deterministic decision-integrity helpers for ConfidenceOS.

These helpers are deliberately small and read-only. They expose engineering
"what if" views, temporary field verification state, handover debt, confidence
debt, and a minimal trust dependency graph without changing sensor confidence.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


CONFIDENCE_WEIGHTS = {
    "calibration": 0.30,
    "stability": 0.20,
    "cross_sensor": 0.30,
    "physical_plausibility": 0.20,
}

TIER_WEIGHTS = {
    "HIGH": 0.0,
    "MEDIUM": 0.5,
    "LOW": 1.0,
    "CRITICAL": 2.0,
}

CONTEXT_WEIGHTS = {
    "INFO": 1.0,
    "MEDIUM": 1.2,
    "WARNING": 1.5,
    "CRITICAL": 2.0,
}

SENSOR_CRITICALITY_BY_TYPE = {
    "level": 3.0,
    "flow_in": 2.0,
    "flow_out": 2.0,
    "pressure": 2.0,
    "temperature": 1.2,
    "valve": 1.5,
}


def tier_from_pct(confidence_pct: float) -> str:
    if confidence_pct >= 80:
        return "HIGH"
    if confidence_pct >= 50:
        return "MEDIUM"
    if confidence_pct >= 20:
        return "LOW"
    return "CRITICAL"


def active_verification_tokens(tokens: list[dict], now: float | None = None) -> list[dict]:
    current = now or time.time()
    active = []
    for token in tokens or []:
        item = dict(token)
        item["active"] = float(item.get("valid_until", 0)) > current
        item["expired"] = not item["active"]
        active.append(item)
    return [item for item in active if item["active"]]


def build_score_sensitivity(sensor_id: str, confidence: dict, role: str = "Engineer") -> dict:
    """Return deterministic score sensitivity scenarios for engineer review."""
    if role != "Engineer":
        return {
            "allowed": False,
            "required_role": "Engineer",
            "message": "Score sensitivity is limited to Engineer view data.",
        }

    sub_scores = confidence.get("sub_scores", {})
    baseline = float(confidence.get("confidence_pct", 0.0))
    scenarios = [
        {
            "scenario": "ignore_calibration",
            "ignored_factor": "calibration",
            "label": "Ignore calibration evidence",
        },
        {
            "scenario": "ignore_mass_balance",
            "ignored_factor": "cross_sensor",
            "label": "Ignore mass-balance / cross-sensor evidence",
        },
        {
            "scenario": "ignore_plausibility",
            "ignored_factor": "physical_plausibility",
            "label": "Ignore physical plausibility evidence",
        },
    ]

    results = []
    for scenario in scenarios:
        ignored = scenario["ignored_factor"]
        score = _renormalized_score(sub_scores, ignored)
        results.append({
            **scenario,
            "confidence_pct": score,
            "tier": tier_from_pct(score),
            "delta_pct": round(score - baseline, 1),
            "method": "removed factor and renormalized remaining confidence weights",
        })

    largest = max(results, key=lambda item: abs(item["delta_pct"])) if results else None
    conclusion = (
        f"{largest['label']} changes {sensor_id} by {largest['delta_pct']} percentage points."
        if largest else
        "No sensitivity scenarios available."
    )

    return {
        "allowed": True,
        "required_role": "Engineer",
        "sensor_id": sensor_id,
        "baseline": {
            "confidence_pct": baseline,
            "tier": confidence.get("tier"),
            "dominant_factor": confidence.get("dominant_factor"),
        },
        "scenarios": results,
        "conclusion": conclusion,
        "deterministic": True,
    }


def update_confidence_debt(
    debt_state: dict[str, dict],
    confidence: list[dict],
    readings: list[dict],
    context: dict | None,
    now: float | None = None,
) -> list[dict]:
    """Accumulate confidence debt in confidence-hours."""
    current = now or time.time()
    context_weight = CONTEXT_WEIGHTS.get((context or {}).get("severity", "INFO"), 1.0)
    reading_type = {
        reading.get("sensor_id"): reading.get("sensor_type")
        for reading in readings or []
    }

    output = []
    for item in confidence or []:
        sid = item.get("sensor_id")
        if not sid:
            continue
        state = debt_state.setdefault(sid, {
            "confidence_debt": 0.0,
            "last_updated": current,
            "last_tier": "HIGH",
            "seconds_below_high": 0.0,
        })
        elapsed_seconds = max(0.0, current - float(state.get("last_updated", current)))
        tier = item.get("tier", "HIGH")
        tier_weight = TIER_WEIGHTS.get(tier, 0.0)
        sensor_type = reading_type.get(sid)
        criticality = SENSOR_CRITICALITY_BY_TYPE.get(sensor_type, 1.0)
        increment = (elapsed_seconds / 3600.0) * tier_weight * criticality * context_weight
        if tier_weight > 0:
            state["seconds_below_high"] = float(state.get("seconds_below_high", 0.0)) + elapsed_seconds
        state["confidence_debt"] = float(state.get("confidence_debt", 0.0)) + increment
        state["last_updated"] = current
        state["last_tier"] = tier

        debt = round(state["confidence_debt"], 4)
        output.append({
            "sensor_id": sid,
            "confidence_debt": debt,
            "confidence_debt_hours": debt,
            "seconds_below_high": round(float(state.get("seconds_below_high", 0.0)), 1),
            "tier": tier,
            "confidence_pct": item.get("confidence_pct"),
            "criticality_weight": criticality,
            "context_weight": context_weight,
            "maintenance_priority": _maintenance_priority_language(sid, debt, tier, context_weight),
        })

    return sorted(output, key=lambda item: item["confidence_debt"], reverse=True)


def annotate_incidents_for_handover(incidents: list[dict]) -> list[dict]:
    annotated = []
    for incident in incidents or []:
        item = dict(incident)
        contract = item.get("action_contract") or {}
        item["handover_required"] = True
        item["decision_freezes"] = [
            {
                "decision": decision,
                "status": "blocked_until_verified",
                "reason": item.get("title", "Active advisory incident"),
                "required_evidence": contract.get("exit_conditions", []),
                "handover_required": True,
            }
            for decision in contract.get("blocked_decisions", [])
        ]
        annotated.append(item)
    return annotated


def build_handover_debt(
    plant_id: str,
    incidents: list[dict],
    confidence: list[dict],
    verification_tokens: list[dict],
    confidence_debt: list[dict],
    now: float | None = None,
) -> dict:
    current = now or time.time()
    entries = []

    for incident in incidents or []:
        if incident.get("handover_required"):
            entries.append({
                "id": f"incident:{incident.get('incident_id', incident.get('title', 'incident'))}",
                "type": "unresolved_incident",
                "severity": incident.get("severity", "INFO"),
                "title": incident.get("title", "Unresolved incident"),
                "required_action": incident.get("first_action"),
                "handover_required": True,
            })
        for freeze in incident.get("decision_freezes", []):
            entries.append({
                "id": f"decision_freeze:{incident.get('incident_id', 'incident')}:{freeze.get('decision')}",
                "type": "active_decision_freeze",
                "severity": incident.get("severity", "INFO"),
                "title": f"Decision freeze: {freeze.get('decision')}",
                "required_action": "Carry blocked decision and exit condition into next shift.",
                "handover_required": True,
            })

    for item in confidence or []:
        if item.get("tier") in ("LOW", "CRITICAL"):
            entries.append({
                "id": f"confidence:{item.get('sensor_id')}",
                "type": "low_confidence_critical_sensor",
                "severity": item.get("tier", "WARNING"),
                "sensor_id": item.get("sensor_id"),
                "title": f"{item.get('sensor_id')} remains {item.get('tier')} confidence",
                "required_action": item.get("recommended_action"),
                "handover_required": True,
            })

    for token in active_verification_tokens(verification_tokens, now=current):
        entries.append({
            "id": f"verification_token:{token.get('token_id')}",
            "type": "active_verification_token",
            "severity": "WARNING",
            "sensor_id": token.get("sensor_id"),
            "title": f"Field verification token active for {token.get('sensor_id')}",
            "valid_until": token.get("valid_until_iso"),
            "required_action": "Confirm token status before relying on temporary field verification.",
            "handover_required": True,
        })

    debt_by_sensor = {item["sensor_id"]: item for item in confidence_debt or []}
    for entry in entries:
        sensor_id = entry.get("sensor_id")
        if sensor_id and sensor_id in debt_by_sensor:
            entry["confidence_debt"] = debt_by_sensor[sensor_id]["confidence_debt"]
            entry["maintenance_priority"] = debt_by_sensor[sensor_id]["maintenance_priority"]

    return {
        "plant_id": plant_id,
        "generated_at": datetime.fromtimestamp(current, timezone.utc).isoformat(),
        "handover_required": bool(entries),
        "count": len(entries),
        "entries": entries,
    }


def build_trust_dependency_graph(
    plant_id: str,
    readings: list[dict],
    confidence: list[dict],
    mass_balance: dict | None,
    incidents: list[dict],
) -> dict:
    confidence_by_id = {item.get("sensor_id"): item for item in confidence or []}
    readings_by_id = {item.get("sensor_id"): item for item in readings or []}
    level = confidence_by_id.get("LT-5100", {})
    flow_in = confidence_by_id.get("FI-2010", {})
    flow_out = confidence_by_id.get("FO-2020", {})
    mb_flags = (mass_balance or {}).get("flags", [])
    lead_incident = (incidents or [{}])[0] if incidents else {}
    contract = lead_incident.get("action_contract") or {}
    blocked = contract.get("blocked_decisions", [])

    nodes = [
        _sensor_node("LT-5100", "measured_level", confidence_by_id, readings_by_id),
        _sensor_node("FI-2010", "inflow_evidence", confidence_by_id, readings_by_id),
        _sensor_node("FO-2020", "outflow_evidence", confidence_by_id, readings_by_id),
        {
            "id": "implied_level",
            "type": "inferred_variable",
            "label": "Flow-implied level",
            "trusted": not mb_flags and _is_high(flow_in) and _is_high(flow_out),
            "evidence": "FI-2010 and FO-2020 mass-balance relationship",
            "value": (mass_balance or {}).get("implied_level"),
        },
        {
            "id": "feed_increase_decision",
            "type": "affected_decision",
            "label": "Feed increase decision",
            "status": "blocked_until_verified" if "increase_feed" in blocked else "allowed_with_monitoring",
            "handover_required": "increase_feed" in blocked,
        },
    ]

    edges = [
        {"source": "LT-5100", "target": "implied_level", "relationship": "contradicts_or_validates"},
        {"source": "FI-2010", "target": "implied_level", "relationship": "supports"},
        {"source": "FO-2020", "target": "implied_level", "relationship": "supports"},
        {"source": "implied_level", "target": "feed_increase_decision", "relationship": "affects_decision"},
    ]

    return {
        "plant_id": plant_id,
        "focus": "LT/FI/FO to implied level to feed increase decision",
        "nodes": nodes,
        "edges": edges,
        "summary": _trust_graph_summary(level, flow_in, flow_out, mb_flags, blocked),
        "deterministic": True,
    }


def _renormalized_score(sub_scores: dict, ignored_factor: str) -> float:
    remaining_weight = sum(
        weight for factor, weight in CONFIDENCE_WEIGHTS.items()
        if factor != ignored_factor
    )
    if remaining_weight <= 0:
        return 0.0
    total = 0.0
    for factor, weight in CONFIDENCE_WEIGHTS.items():
        if factor == ignored_factor:
            continue
        total += (weight / remaining_weight) * float(sub_scores.get(factor, 1.0))
    return round(max(0.0, min(100.0, total * 100.0)), 1)


def _maintenance_priority_language(sensor_id: str, debt: float, tier: str, context_weight: float) -> str:
    if debt >= 2.0 or tier == "CRITICAL":
        return f"{sensor_id}: highest maintenance priority from accumulated confidence debt and active operating context."
    if debt >= 0.5 or tier == "LOW":
        return f"{sensor_id}: elevated maintenance priority from confidence debt."
    if tier == "MEDIUM" and context_weight > 1.0:
        return f"{sensor_id}: monitor confidence debt during abnormal context."
    return f"{sensor_id}: routine monitoring; confidence debt remains low."


def _sensor_node(sensor_id: str, role: str, confidence_by_id: dict, readings_by_id: dict) -> dict:
    conf = confidence_by_id.get(sensor_id, {})
    reading = readings_by_id.get(sensor_id, {})
    return {
        "id": sensor_id,
        "type": "sensor",
        "role": role,
        "confidence_pct": conf.get("confidence_pct"),
        "tier": conf.get("tier", "UNKNOWN"),
        "trusted": _is_high(conf),
        "value": reading.get("value"),
        "unit": reading.get("unit"),
    }


def _is_high(confidence: dict) -> bool:
    return confidence.get("tier") == "HIGH"


def _trust_graph_summary(level: dict, flow_in: dict, flow_out: dict, mb_flags: list[dict], blocked: list[str]) -> str:
    if "increase_feed" in blocked:
        return "Feed increase is blocked until level integrity is verified."
    if level.get("tier") in ("LOW", "CRITICAL") and _is_high(flow_in) and _is_high(flow_out):
        return "Level indication is less trusted than independent flow evidence."
    if mb_flags:
        return "Mass-balance divergence reduces trust in the inferred level picture."
    return "Level, flow, and feed-increase trust dependencies are currently nominal."
