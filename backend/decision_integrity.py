"""
decision_integrity.py - Deterministic decision-integrity helpers for ConfidenceOS.

These helpers are deliberately small and read-only. They expose engineering
"what if" views, temporary field verification state, handover debt, confidence
debt, and a minimal trust dependency graph without changing sensor confidence.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from asset_model import (
    affected_decisions,
    affected_decision_by_contract,
    criticality_weight,
    load_asset_model,
    mass_balance_validation,
)
from confidence import ConfidenceWeights as _CW

# Single source of truth for weights — defined in confidence.py:ConfidenceWeights
_DEFAULT_WEIGHTS = _CW()
CONFIDENCE_WEIGHTS = {
    "calibration": _DEFAULT_WEIGHTS.calibration,
    "stability": _DEFAULT_WEIGHTS.stability,
    "cross_sensor": _DEFAULT_WEIGHTS.cross_sensor,
    "physical_plausibility": _DEFAULT_WEIGHTS.physical_plausibility,
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
        item = normalize_verification_task(token, current)
        active.append(item)
    return [item for item in active if item["active"]]


def normalize_verification_task(token: dict, now: float | None = None) -> dict:
    """Return old verification-token records as field verification tasks."""
    current = now or time.time()
    item = dict(token or {})
    sensor_id = item.get("sensor_id", "UNKNOWN")
    valid_until = _timestamp_value(item.get("valid_until") or item.get("valid_until_iso"), current)
    expired = valid_until <= current
    state = item.get("state") or "REQUESTED"
    if expired and state not in ("ACCEPTED", "EXPIRED"):
        state = "EXPIRED"
    task_id = item.get("task_id") or item.get("token_id") or f"verification:{sensor_id}:{int(item.get('created_at', current))}"
    token_id = item.get("token_id") or task_id
    return {
        **item,
        "task_id": task_id,
        "token_id": token_id,
        "sensor_id": sensor_id,
        "state": state,
        "assigned_role": item.get("assigned_role", "Maintenance"),
        "verification_method": item.get("verification_method") or item.get("verification_type", "local_field_check"),
        "verification_type": item.get("verification_type") or item.get("verification_method", "local_field_check"),
        "evidence_required": item.get("evidence_required", ["local level indication", "field operator note"]),
        "valid_until": valid_until,
        "accepted_by": item.get("accepted_by"),
        "handover_required": state not in ("ACCEPTED", "EXPIRED"),
        "active": not expired and state not in ("ACCEPTED", "EXPIRED"),
        "expired": expired or state == "EXPIRED",
        "confidence_override": False,
        "usable_as_reference": item.get("usable_as_reference", False),
    }


def ensure_verification_tasks(
    existing_tasks: list[dict],
    incidents: list[dict],
    confidence: list[dict],
    plant_context: dict | None,
    now: float | None = None,
) -> list[dict]:
    """Generate requested verification tasks when trust quarantine blocks handover."""
    current = now or time.time()
    tasks_by_id = {
        normalize_verification_task(task, current)["task_id"]: normalize_verification_task(task, current)
        for task in existing_tasks or []
    }
    context_state = (plant_context or {}).get("state")
    handover_blocked = any(
        "accept_handover_without_verification" in (incident.get("action_contract") or {}).get("blocked_decisions", [])
        for incident in incidents or []
    )
    requested_sensors = set()
    for item in confidence or []:
        if item.get("trust_state") == "QUARANTINED" or (
            item.get("tier") in ("LOW", "CRITICAL") and item.get("decision_basis_allowed") is False
        ):
            requested_sensors.add(item.get("sensor_id"))
    if context_state == "MANUAL_VERIFICATION_REQUIRED" or handover_blocked:
        for incident in incidents or []:
            for sensor_id in incident.get("affected_sensors", []):
                if sensor_id:
                    requested_sensors.add(sensor_id)

    for sensor_id in sorted(sid for sid in requested_sensors if sid):
        task_id = f"verification-task:{sensor_id}"
        existing = tasks_by_id.get(task_id)
        if existing and existing.get("state") not in ("ACCEPTED", "EXPIRED"):
            continue
        valid_until = current + 30 * 60
        tasks_by_id[task_id] = normalize_verification_task({
            "task_id": task_id,
            "token_id": task_id,
            "plant_id": "plant-a",
            "sensor_id": sensor_id,
            "state": "REQUESTED",
            "assigned_role": "Maintenance",
            "verification_method": "local_field_check",
            "verification_type": "field_check",
            "evidence_required": ["local indication", "field photo or operator note", "time-stamped confirmation"],
            "created_at": current,
            "created_at_iso": datetime.fromtimestamp(current, timezone.utc).isoformat(),
            "valid_until": valid_until,
            "valid_until_iso": datetime.fromtimestamp(valid_until, timezone.utc).isoformat(),
            "note": "Generated because trust quarantine or handover block requires field verification.",
            "handover_required": True,
        }, current)

    return sorted(tasks_by_id.values(), key=lambda item: (item.get("state") == "ACCEPTED", item.get("sensor_id", "")))


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
        criticality = criticality_weight(sid, sensor_type)
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
            "id": f"verification_task:{token.get('task_id')}",
            "type": "active_verification_token",
            "task_type": "active_verification_task",
            "severity": "WARNING",
            "sensor_id": token.get("sensor_id"),
            "title": f"Field verification task {token.get('state')} for {token.get('sensor_id')}",
            "valid_until": token.get("valid_until_iso"),
            "state": token.get("state"),
            "required_action": "Complete and accept field verification before handover acceptance.",
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
        "handover_acceptance": "blocked" if entries else "unblocked",
        "handover_acceptance_blocked": bool(entries),
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
    asset_model = load_asset_model()
    relationship = mass_balance_validation(asset_model)
    # Tags are sourced from the active asset model's mass-balance relationship.
    # Neutral fallbacks only — never literal refinery tag IDs — so model switches stay clean.
    level_tag = relationship.get("validated_tag", "")
    flow_tags = relationship.get("source_tags", [])
    inferred_variable = relationship.get("inferred_variable", "implied_level")
    model_decisions = affected_decisions(asset_model)
    primary_decision = next(
        (
            item for item in model_decisions
            if item.get("contract_decision") != "accept_handover_without_verification"
        ),
        {},
    )
    decision_id = primary_decision.get("id", "primary_operating_decision")
    decision_label = primary_decision.get("label", "Primary operating decision")
    decision_contract = primary_decision.get("contract_decision", decision_id)
    confidence_by_id = {item.get("sensor_id"): item for item in confidence or []}
    readings_by_id = {item.get("sensor_id"): item for item in readings or []}
    level = confidence_by_id.get(level_tag, {})
    flow_in = confidence_by_id.get(flow_tags[0], {}) if flow_tags else {}
    flow_out = confidence_by_id.get(flow_tags[1], {}) if len(flow_tags) > 1 else {}
    mb_flags = (mass_balance or {}).get("flags", [])
    lead_incident = (incidents or [{}])[0] if incidents else {}
    contract = lead_incident.get("action_contract") or {}
    blocked = contract.get("blocked_decisions", [])

    nodes = [
        _sensor_node(level_tag, "measured_level", confidence_by_id, readings_by_id),
        *[
            _sensor_node(tag, "flow_evidence", confidence_by_id, readings_by_id)
            for tag in flow_tags
        ],
        {
            "id": inferred_variable,
            "type": "inferred_variable",
            "label": "Flow-implied level",
            "trusted": not mb_flags and _is_high(flow_in) and _is_high(flow_out),
            "evidence": relationship.get("description", "Mass-balance validation relationship"),
            "value": (mass_balance or {}).get("implied_level"),
            "asset_relationship": relationship.get("id"),
        },
        {
            "id": decision_id,
            "type": "affected_decision",
            "label": decision_label,
            "status": "blocked_until_verified" if decision_contract in blocked else "allowed_with_monitoring",
            "handover_required": decision_contract in blocked,
            "depends_on": primary_decision.get("depends_on", []),
        },
    ]

    edges = [
        {"source": level_tag, "target": inferred_variable, "relationship": "contradicts_or_validates"},
        *[
            {"source": tag, "target": inferred_variable, "relationship": "supports"}
            for tag in flow_tags
        ],
        {"source": inferred_variable, "target": decision_id, "relationship": "affects_decision"},
    ]

    return {
        "plant_id": plant_id,
        "focus": f"{level_tag}/{','.join(flow_tags)} to {inferred_variable} to {decision_label}",
        "nodes": nodes,
        "edges": edges,
        "summary": _trust_graph_summary(level, flow_in, flow_out, mb_flags, blocked, decision_contract, decision_label),
        "asset_model_id": asset_model.get("model_id"),
        "equipment_id": asset_model.get("equipment", {}).get("equipment_id"),
        "read_only_trust_layer": asset_model.get("read_only_trust_layer", True),
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


def _timestamp_value(value, fallback: float) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return fallback + 30 * 60


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


def _trust_graph_summary(level: dict, flow_in: dict, flow_out: dict, mb_flags: list[dict], blocked: list[str], decision_contract: str, decision_label: str) -> str:
    if decision_contract in blocked:
        return f"{decision_label} is blocked until level integrity is verified."
    if level.get("tier") in ("LOW", "CRITICAL") and _is_high(flow_in) and _is_high(flow_out):
        return "Level indication is less trusted than independent flow evidence."
    if mb_flags:
        return "Mass-balance divergence reduces trust in the inferred level picture."
    return "Level, flow, and feed-increase trust dependencies are currently nominal."
