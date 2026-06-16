"""
screen_generator.py - Deterministic generated Runtime screen manifests.
"""

from __future__ import annotations

import time

from assumptions import confidence_formula_expression, load_assumptions
from decision_integrity import build_score_sensitivity
from model_graph import equipment_signals, get_assets, get_model_graph, get_navigation
from template_library import load_context_policies, load_role_policies, template_by_id, validate_assignments


def generate_screen_manifest(
    role: str = "Operator",
    context: str = "auto",
    live_state: dict | None = None,
    assignments: list[dict] | None = None,
    build_context: dict | None = None,
) -> dict:
    live_state = live_state or {}
    build_context = build_context or {}
    context_state = _resolve_context(context, live_state)
    role_policy = load_role_policies().get("policies", {}).get(role) or load_role_policies().get("policies", {}).get("Operator", {})
    context_policy = load_context_policies().get("policies", {}).get(context_state, {})
    validation = validate_assignments(assignments or [])
    stress = _is_stress(live_state, context_state)
    build_id = build_context.get("build_id", "runtime-ad-hoc")
    validation_status = build_context.get("validation_status") or ("PASS_WITH_WARNINGS" if validation.get("warnings") else "PASS")
    receipts = build_context.get("receipts", [])
    source_tags = build_context.get("source_tags", [])
    build_context = {
        **build_context,
        "build_id": build_id,
        "validation_status": validation_status,
        "validation": build_context.get("validation") or validation,
        "source_tags": source_tags,
    }
    warnings = _validation_messages(build_context.get("validation") or validation)
    plant_id = live_state.get("plant_id", "plant-a")
    navigation = get_navigation()
    unit = _first_unit(navigation)
    unit_id = unit.get("id", "unit-runtime")
    unit_name = unit.get("name", "Generated Unit")
    assets = get_assets()
    faceplates = [
        _faceplate_for_asset(asset, live_state, role, context_state, assignments or [], build_context)
        for asset in assets
        if asset.get("asset_type") in ("process_vessel", "valve", "flow_pair", "pump")
    ]
    faceplates = [item for item in faceplates if item]
    situations = _situations(live_state, build_context, role, context_state, validation_status)
    screens = [
        {
            **_generation_metadata(
                build_context=build_context,
                generated_id=f"{build_id}:{navigation.get('id', plant_id)}:plant-overview",
                asset_id=navigation.get("id", plant_id),
                template_id="plant_overview",
                role=role,
                context_state=context_state,
                validation_status=validation_status,
                source_tags=source_tags,
                generated_because=[
                    f"{navigation.get('name', 'Plant')} overview generated from asset model hierarchy.",
                    "Instrument integrity overview is required for Runtime navigation.",
                ],
                warnings=warnings,
            ),
            "screen_id": "plant-overview",
            "screen_type": "plant_overview",
            "title": f"{navigation.get('name', 'Plant')} Instrument Integrity Overview",
            "sections": ["semantic_navigation", "trust_hotspots", "unresolved_situations"],
        },
        {
            **_generation_metadata(
                build_context=build_context,
                generated_id=f"{build_id}:{unit_id}:runtime",
                asset_id=unit_id,
                template_id="unit_overview",
                role=role,
                context_state=context_state,
                validation_status=validation_status,
                source_tags=source_tags,
                generated_because=[
                    f"{unit_name} Runtime generated from semantic plant hierarchy.",
                    "Situation workspace and generated faceplates are required for operator use.",
                ],
                warnings=warnings,
            ),
            "screen_id": f"{unit_id}-runtime",
            "screen_type": "unit_overview",
            "title": f"{unit_name} Runtime",
            "sections": ["situation_workspace", "generated_faceplates", "shift_channel"],
        },
    ]
    role_sections = _role_sections(role, live_state, build_context, context_state, validation_status)
    trust_rubric_receipts = _trust_rubric_receipts(live_state)
    worst_trust_exception = _worst_trust_exception(live_state.get("confidence", []))
    interaction_compression_estimate = _interaction_compression_estimate(situations, live_state.get("confidence", []))
    process_mimic = _process_mimic(faceplates, live_state, situations)
    stress_mode_panel = _stress_mode_panel(
        live_state=live_state,
        situations=situations,
        build_context=build_context,
        role=role,
        context_state=context_state,
        validation_status=validation_status,
        active=stress,
    )

    return {
        "manifest_id": f"runtime:{role}:{context_state}",
        "build_id": build_id,
        "route": "/runtime",
        "generated_at": time.time(),
        "role": role,
        "context": context_state,
        "validation_status": validation_status,
        "stress_mode": stress,
        "source": "asset_model_and_template_library",
        "read_only_trust_layer": True,
        "compiler_pipeline": "Raw Tags -> Asset Graph -> Template Binding -> Validation -> Screen Generation -> Publish Readiness -> Runtime",
        "navigation": navigation,
        "role_policy": role_policy,
        "context_policy": context_policy,
        "validation": build_context.get("validation") or validation,
        "semantic_zoom": ["plant", "area", "unit", "module", "equipment", "signal"],
        "provenance": {
            "asset_model_id": get_model_graph().get("model_id"),
            "build_id": build_id,
            "validation_status": validation_status,
            "role_policy": role,
            "context_policy": context_state,
            "template_assignments": assignments or [],
            "source_tags": build_context.get("source_tags", []),
            "receipts": receipts,
        },
        "screens": screens,
        "faceplates": faceplates,
        "receipts": receipts,
        "situations": situations,
        "operating_basis": _operating_basis(live_state, situations),
        "trust_rubric_receipts": trust_rubric_receipts,
        "worst_trust_exception": worst_trust_exception,
        "process_mimic": process_mimic,
        "interaction_compression_estimate": interaction_compression_estimate,
        "role_sections": role_sections,
        "stress_mode_panel": stress_mode_panel,
}


def _first_unit(navigation: dict) -> dict:
    for area in navigation.get("areas", []) or []:
        units = area.get("units", []) or []
        if units:
            return units[0]
    return {"id": "unit-runtime", "name": "Generated Unit"}


def _primary_equipment_id() -> str:
    for asset in get_assets():
        if asset.get("asset_type") in ("process_vessel", "pump", "valve", "flow_pair"):
            return asset.get("asset_id") or "primary-equipment"
    return "primary-equipment"


def _primary_level_signal_id() -> str:
    for signal in get_model_graph().get("signals", []):
        if signal.get("role") == "primary_level" or signal.get("sensor_type") == "level":
            return signal.get("tag") or "primary-level"
    return "primary-level"


def equipment_manifest(equipment_id: str, role: str, live_state: dict | None = None, assignments: list[dict] | None = None) -> dict:
    asset = next((item for item in get_assets() if item.get("asset_id") == equipment_id), None)
    if not asset:
        return {}
    return _faceplate_for_asset(asset, live_state or {}, role, "auto", assignments or [], {})


def _faceplate_for_asset(
    asset: dict,
    live_state: dict,
    role: str,
    context_state: str,
    assignments: list[dict],
    build_context: dict | None = None,
) -> dict:
    build_context = build_context or {}
    asset_id = asset.get("asset_id")
    assignment = next((item for item in assignments if item.get("asset_id") == asset_id), {})
    template_id = assignment.get("template_id") or asset.get("template_id")
    template = template_by_id(template_id)
    if not template:
        return {}
    signals = equipment_signals(asset_id)
    readings_by_id = {item.get("sensor_id"): item for item in live_state.get("readings", [])}
    confidence_by_id = {item.get("sensor_id"): item for item in live_state.get("confidence", [])}
    signal_rows = []
    for signal in signals:
        tag = signal.get("tag")
        confidence = confidence_by_id.get(tag)
        signal_rows.append({
            **signal,
            "reading": readings_by_id.get(tag),
            "confidence": confidence,
            "trust_state": _signal_trust_state(confidence, readings_by_id.get(tag)),
            "decision_basis_allowed": (confidence or {}).get("decision_basis_allowed", True),
            "trust_reason": (confidence or {}).get("trust_reason"),
        })
    source_tags = [signal.get("tag") for signal in signals if signal.get("tag")]
    metadata = _generation_metadata(
        build_context=build_context,
        generated_id=f"{build_context.get('build_id', 'runtime-ad-hoc')}:{asset_id}",
        asset_id=asset_id,
        template_id=template_id,
        role=role,
        context_state=context_state,
        validation_status=build_context.get("validation_status", "PASS"),
        source_tags=source_tags,
        generated_because=[
            f"{asset_id} is assigned template {template_id}.",
            "Faceplate generated from asset model signal binding and role visibility policy.",
        ] + _mutation_receipt_lines(build_context),
        warnings=_validation_messages(build_context.get("validation", {}), asset_id=asset_id, template_id=template_id),
    )
    return {
        **metadata,
        "equipment_id": asset_id,
        "title": asset.get("name", asset_id),
        "asset_type": asset.get("asset_type"),
        "template_label": template.get("label"),
        "role": role,
        "context": context_state,
        "sections": template.get("role_visibility", {}).get(role, template.get("generated_ui_sections", [])),
        "signals": signal_rows,
        "provenance": {
            "generated_from": ["asset_model.json", "equipment_templates.json", "role_policies.json", "context_policies.json"],
            "build_id": build_context.get("build_id", "runtime-ad-hoc"),
            "validation_status": build_context.get("validation_status", "PASS"),
            "template_id": template_id,
            "asset_id": asset_id,
            "source_tags": source_tags,
            "approved": assignment.get("approved", False),
        },
    }


def _generation_metadata(
    build_context: dict,
    generated_id: str,
    asset_id: str,
    template_id: str,
    role: str,
    context_state: str,
    validation_status: str,
    source_tags: list,
    generated_because: list[str],
    warnings: list[str] | None = None,
) -> dict:
    return {
        "generated_id": generated_id,
        "build_id": build_context.get("build_id", "runtime-ad-hoc"),
        "asset_id": asset_id,
        "template_id": template_id,
        "template_version": "1.0",
        "source_tags": source_tags or [],
        "role_policy": role,
        "context_policy": context_state,
        "validation_status": validation_status,
        "receipt": {
            "generated_because": generated_because,
            "warnings": warnings or [],
            "source_files": [
                "asset_model.json",
                "equipment_templates.json",
                "role_policies.json",
                "context_policies.json",
            ],
        },
    }


def _resolve_context(context: str, live_state: dict) -> str:
    if context and context != "auto":
        return context
    plant_context = live_state.get("plant_context") or {}
    inferred = live_state.get("mode", {}).get("inferred_mode")
    return plant_context.get("state") or inferred or "STEADY_STATE"


def _situations(
    live_state: dict,
    build_context: dict | None = None,
    role: str = "Operator",
    context_state: str = "STEADY_STATE",
    validation_status: str = "PASS",
) -> list[dict]:
    build_context = build_context or {}
    incidents = live_state.get("incidents") or []
    decorated = []
    for index, incident in enumerate(incidents):
        asset_id = incident.get("asset_id") or _primary_equipment_id()
        source_tags = _situation_source_tags(incident, build_context)
        decorated.append({
            **_generation_metadata(
                build_context=build_context,
                generated_id=f"{build_context.get('build_id', 'runtime-ad-hoc')}:situation:{incident.get('incident_id', index)}",
                asset_id=asset_id,
                template_id="abnormal_situation",
                role=role,
                context_state=context_state,
                validation_status=validation_status,
                source_tags=source_tags,
                generated_because=[
                    "Abnormal situation generated from collapsed advisory incident.",
                    "Situation workspace requires operating basis, evidence, action contract, and timeline.",
                ] + _mutation_receipt_lines(build_context),
                warnings=_validation_messages(build_context.get("validation", {}), asset_id=asset_id),
            ),
            "alarm_collapse_receipt": _alarm_collapse_receipt(incident),
            "decision_time_score": _decision_time_score(incident, live_state.get("confidence", [])),
            **incident,
        })
    return decorated


def _operating_basis(live_state: dict, situations: list[dict]) -> dict:
    lead = situations[0] if situations else {}
    contract = lead.get("action_contract") or {}
    return {
        "abnormal_situation": lead.get("title") or "Normal operation",
        "do_not_trust": contract.get("do_not_use", []),
        "trusted_substitutes": contract.get("trusted_substitutes", []),
        "first_safe_action": contract.get("first_safe_action") or lead.get("first_action") or "Continue normal monitoring.",
        "operator_single_safe_move": contract.get("operator_single_safe_move") or contract.get("first_safe_action") or lead.get("first_action") or "Continue normal monitoring.",
        "decision_freeze": contract.get("blocked_decisions", []),
        "exit_condition": contract.get("exit_conditions", []),
        "evidence": lead.get("evidence_refs", []),
        "trust_quarantine": lead.get("trust_quarantine", {}),
        "alarm_collapse_receipt": _alarm_collapse_receipt(lead) if lead else {},
        "decision_time_score": _decision_time_score(lead, live_state.get("confidence", [])) if lead else _decision_time_score({}, live_state.get("confidence", [])),
    }


def _role_sections(
    role: str,
    live_state: dict,
    build_context: dict | None = None,
    context_state: str = "STEADY_STATE",
    validation_status: str = "PASS",
) -> list[dict]:
    build_context = build_context or {}
    if role == "Maintenance":
        tasks = live_state.get("verification_tasks") or live_state.get("verification_tokens", [])
        confidence = live_state.get("confidence", [])
        confidence_by_id = {item.get("sensor_id"): item for item in confidence or []}
        rows = [
            {"section": "verification_task", "items": tasks},
            {"section": "calibration_context", "items": _calibration_context(confidence)},
            {"section": "device_health", "items": _device_health(confidence)},
            {"section": "confidence_debt", "items": live_state.get("confidence_debt", [])},
            {"section": "field_check_status", "items": [
                {
                    "sensor_id": task.get("sensor_id"),
                    "state": task.get("state"),
                    "verification_method": task.get("verification_method"),
                    "confidence_tier": confidence_by_id.get(task.get("sensor_id"), {}).get("tier"),
                }
                for task in tasks
            ]},
        ]
    elif role == "Engineer":
        confidence = live_state.get("confidence", [])
        primary_level = _primary_level_signal_id()
        lead_confidence = next((item for item in confidence if item.get("sensor_id") == primary_level), confidence[0] if confidence else {})
        build_id = build_context.get("build_id", "runtime-ad-hoc")
        rows = [
            {"section": "signal_mapping", "items": get_model_graph().get("signals", [])},
            {"section": "template_receipt", "items": build_context.get("receipts", [])},
            {"section": "assumptions_used", "items": _assumptions_used()},
            {"section": "score_sensitivity", "items": [build_score_sensitivity(lead_confidence.get("sensor_id", primary_level), lead_confidence, role="Engineer")] if lead_confidence else []},
            {"section": "validation_warnings", "items": (build_context.get("validation") or {}).get("warnings", []) + (build_context.get("validation") or {}).get("blocking", [])},
            {"section": "build_publish_provenance", "items": [{
                "build_id": build_id,
                "published_build_id": build_context.get("published_build_id"),
                "runtime_source": build_context.get("runtime_source"),
                "validation_status": build_context.get("validation_status"),
                "source_tags": build_context.get("source_tags", []),
            }]},
        ]
    elif role in ("Manager", "Auditor"):
        debt = live_state.get("handover_debt") or {}
        freezes = [
            freeze
            for incident in live_state.get("incidents", []) or []
            for freeze in incident.get("decision_freezes", [])
        ]
        rows = [
            {"section": "unresolved_handover_debt", "items": debt.get("entries", [])},
            {"section": "decision_freeze_state", "items": freezes},
            {"section": "handover_acceptance", "items": [{
                "state": debt.get("handover_acceptance", "unblocked"),
                "blocked": debt.get("handover_acceptance_blocked", False),
                "blocking_items": debt.get("count", 0),
            }]},
            {"section": "timeline_evidence", "items": live_state.get("incident_timeline", [])},
            {"section": "published_build_id", "items": [{"build_id": build_context.get("published_build_id") or build_context.get("build_id")}]},
        ]
    else:
        basis = _operating_basis(live_state, _situations(live_state, build_context, role, context_state, validation_status))
        rows = [
            {"section": "single_safe_move", "items": [basis.get("operator_single_safe_move")]},
            {"section": "operating_basis", "items": [basis]},
            {"section": "do_not_trust", "items": basis.get("do_not_trust", [])},
            {"section": "trusted_substitute", "items": basis.get("trusted_substitutes", [])},
            {"section": "decision_freeze", "items": basis.get("decision_freeze", [])},
            {"section": "exit_condition", "items": basis.get("exit_condition", [])},
        ]

    return [
        {
            **_generation_metadata(
                build_context=build_context,
                generated_id=f"{build_context.get('build_id', 'runtime-ad-hoc')}:role:{role}:{row['section']}",
                asset_id=live_state.get("plant_id", "plant-a"),
                template_id="role_section",
                role=role,
                context_state=context_state,
                validation_status=validation_status,
                source_tags=build_context.get("source_tags", []),
                generated_because=[
                    f"{row['section']} is visible for {role} role policy.",
                    "Role-specific section generated from role_policies.json.",
                ],
                warnings=_validation_messages(build_context.get("validation", {})),
            ),
            **row,
        }
        for row in rows
    ]


def _stress_mode_panel(
    live_state: dict,
    situations: list[dict],
    build_context: dict,
    role: str,
    context_state: str,
    validation_status: str,
    active: bool,
) -> dict:
    basis = _operating_basis(live_state, situations)
    return {
        **_generation_metadata(
            build_context=build_context,
            generated_id=f"{build_context.get('build_id', 'runtime-ad-hoc')}:stress-mode:{context_state}",
            asset_id=live_state.get("plant_id", "plant-a"),
            template_id="abnormal_situation",
            role=role,
            context_state=context_state,
            validation_status=validation_status,
            source_tags=build_context.get("source_tags", []),
            generated_because=[
                "Stress-mode panel generated from context policy.",
                "WARNING/CRITICAL operating context requires nonessential panels to be removed.",
            ] + _mutation_receipt_lines(build_context),
            warnings=_validation_messages(build_context.get("validation", {})),
        ),
        "active": active,
        "sections": [
            "abnormal_situation",
            "operator_single_safe_move",
            *(
                ["verification_required"]
                if build_context.get("template_mutations", {}).get("require_manual_verification_when_level_quarantined")
                else []
            ),
            "do_not_trust",
            "trusted_substitute",
            "decision_freeze",
            "exit_condition",
            "alarm_collapse_receipt",
            "decision_time_score",
        ],
        "operating_basis": basis,
        "grounded_explanation_disabled": active,
        "grounded_explanation_message": "Grounded explanation disabled during active decision freeze. Use operating-basis workflow.",
    }


def _is_stress(live_state: dict, context_state: str) -> bool:
    severity = (live_state.get("plant_context") or {}).get("severity")
    return severity in ("WARNING", "CRITICAL") or context_state in ("WARNING", "CRITICAL", "MASS_BALANCE_DIVERGENCE", "MANUAL_VERIFICATION_REQUIRED")


def _validation_messages(validation: dict, asset_id: str | None = None, template_id: str | None = None) -> list[str]:
    messages = []
    for item in validation.get("warnings", []) + validation.get("blocking", []):
        if asset_id and item.get("asset_id") not in (None, asset_id):
            continue
        if template_id and item.get("template_id") not in (None, template_id):
            continue
        message = item.get("message")
        if message:
            messages.append(message)
    return messages


def _situation_source_tags(incident: dict, build_context: dict) -> list[str]:
    tags = []
    for field in ("affected_sensors", "sensor_ids", "do_not_use"):
        values = incident.get(field)
        if isinstance(values, list):
            tags.extend(values)
    tags.extend(build_context.get("source_tags", []))
    return sorted({tag for tag in tags if isinstance(tag, str)})


def _calibration_context(confidence: list[dict]) -> list[dict]:
    rows = []
    for item in confidence or []:
        calibration = None
        for evidence in item.get("evidence", []) or []:
            if evidence.get("category") == "calibration":
                calibration = evidence
                break
        rows.append({
            "sensor_id": item.get("sensor_id"),
            "tier": item.get("tier"),
            "confidence_pct": item.get("confidence_pct"),
            "calibration_status": calibration.get("status") if calibration else "UNKNOWN",
            "calibration_message": calibration.get("message") if calibration else "Calibration evidence not available.",
        })
    return rows


def _device_health(confidence: list[dict]) -> list[dict]:
    return [
        {
            "sensor_id": item.get("sensor_id"),
            "trust_state": item.get("trust_state", "TRUSTED"),
            "tier": item.get("tier"),
            "confidence_pct": item.get("confidence_pct"),
            "decision_basis_allowed": item.get("decision_basis_allowed", True),
            "trust_reason": item.get("trust_reason"),
        }
        for item in confidence or []
    ]


def _assumptions_used() -> list[dict]:
    assumptions = load_assumptions()
    keys = [
        "confidence_weights",
        "calibration_interval",
        "mass_balance_tolerance",
        "flow_to_level_conversion_factor",
        "startup_thresholds",
        "stale_reading_threshold",
        "operating_envelopes",
    ]
    return [
        {
            "assumption_id": key,
            **assumptions.get(key, {}),
        }
        for key in keys
        if key in assumptions
    ]


def _trust_rubric_receipts(live_state: dict) -> list[dict]:
    assumptions = _assumptions_used()
    assumption_ids = [item.get("assumption_id") for item in assumptions if item.get("assumption_id")]
    receipts = []
    for item in live_state.get("confidence", []) or []:
        evidence = item.get("evidence", []) or []
        counter = [
            row.get("message")
            for row in evidence
            if row.get("status") in ("BAD", "DEGRADED") or row.get("severity") in ("WARNING", "CRITICAL")
        ]
        receipts.append({
            "sensor_id": item.get("sensor_id"),
            "trust_state": item.get("trust_state", _signal_trust_state(item, {})),
            "confidence_pct": item.get("confidence_pct"),
            "tier": item.get("tier"),
            "formula": confidence_formula_expression(),
            "sub_scores": item.get("sub_scores", {}),
            "dominant_factor": item.get("dominant_factor", "none"),
            "strongest_evidence": _strongest_evidence(evidence),
            "counter_evidence": [msg for msg in counter if msg],
            "verdict": item.get("trust_state") or item.get("tier") or "TRUSTED",
            "recommended_action": item.get("recommended_action", "Continue normal monitoring."),
            "related_assumptions": assumption_ids,
            "governed_rubric": True,
            "not_probability": True,
        })
    return receipts


def _strongest_evidence(evidence: list[dict]) -> list[str]:
    if not evidence:
        return []
    ranked = sorted(
        evidence,
        key=lambda row: (0 if row.get("severity") in ("CRITICAL", "WARNING") else 1, row.get("score", 1.0)),
    )
    return [row.get("message") for row in ranked[:3] if row.get("message")]


def _worst_trust_exception(confidence: list[dict]) -> dict:
    rank = {
        "QUARANTINED": 0,
        "UNAVAILABLE": 1,
        "DEGRADED": 2,
        "NO_CONFIDENCE_RESULT": 3,
        "SUBSTITUTED": 4,
        "TRUSTED": 5,
        "HIGH": 5,
        "NO_LIVE_SAMPLE": 6,
    }
    rows = []
    for item in confidence or []:
        trust_state = item.get("trust_state")
        if not trust_state:
            trust_state = "DEGRADED" if item.get("tier") in ("MEDIUM", "LOW", "CRITICAL") else "TRUSTED"
        rows.append({
            "sensor_id": item.get("sensor_id"),
            "trust_state": trust_state,
            "confidence_pct": item.get("confidence_pct"),
            "tier": item.get("tier"),
            "reason": item.get("trust_reason") or (item.get("reasons") or ["No active trust exception."])[0],
            "rank": rank.get(str(trust_state).upper(), 5),
            "decision_basis_allowed": item.get("decision_basis_allowed", True),
        })
    if not rows:
        return {
            "trust_state": "NO_LIVE_SAMPLE",
            "label": "Awaiting live trust evidence",
            "decision_basis_allowed": False,
        }
    lead = sorted(rows, key=lambda row: (row["rank"], row.get("confidence_pct") or 100))[0]
    lead["label"] = (
        f"{lead['trust_state']} {lead.get('sensor_id')}"
        if lead["rank"] <= 2 else
        "No active trust exceptions"
    )
    return lead


def _interaction_compression_estimate(situations: list[dict], confidence: list[dict]) -> dict:
    if situations:
        return _decision_time_score(situations[0], confidence)
    return _decision_time_score({}, confidence)


def _process_mimic(faceplates: list[dict], live_state: dict, situations: list[dict]) -> dict:
    graph = get_model_graph()
    relationships = graph.get("relationships", [])
    mass_balance = next((rel for rel in relationships if rel.get("type") == "mass_balance_validation"), {})
    confidence_by_id = {item.get("sensor_id"): item for item in live_state.get("confidence", []) or []}
    readings_by_id = {item.get("sensor_id"): item for item in live_state.get("readings", []) or []}
    validated_tag = mass_balance.get("validated_tag")
    source_tags = mass_balance.get("source_tags", [])
    lead = situations[0] if situations else {}
    contract = lead.get("action_contract") or {}
    equipment = []
    for faceplate in faceplates or []:
        equipment.append({
            "equipment_id": faceplate.get("equipment_id"),
            "title": faceplate.get("title"),
            "asset_type": faceplate.get("asset_type"),
            "template_id": faceplate.get("template_id"),
            "signals": [
                _mimic_signal(signal.get("tag"), confidence_by_id, readings_by_id)
                for signal in faceplate.get("signals", []) or []
            ],
        })
    return {
        "title": "Generated process trust mimic",
        "asset_model_id": graph.get("model_id"),
        "equipment": equipment,
        "validated_signal": _mimic_signal(validated_tag, confidence_by_id, readings_by_id) if validated_tag else {},
        "substitute_signals": [_mimic_signal(tag, confidence_by_id, readings_by_id) for tag in source_tags],
        "decision_freezes": contract.get("blocked_decisions", []),
        "single_safe_move": contract.get("operator_single_safe_move") or contract.get("first_safe_action"),
        "relationship_id": mass_balance.get("id"),
        "relationship_label": mass_balance.get("description") or "Mass-balance validation relationship",
        "read_only_trust_layer": True,
    }


def _mimic_signal(sensor_id: str | None, confidence_by_id: dict, readings_by_id: dict) -> dict:
    if not sensor_id:
        return {}
    confidence = confidence_by_id.get(sensor_id, {})
    reading = readings_by_id.get(sensor_id, {})
    return {
        "sensor_id": sensor_id,
        "trust_state": confidence.get("trust_state", _signal_trust_state(confidence, reading)),
        "confidence_pct": confidence.get("confidence_pct"),
        "tier": confidence.get("tier"),
        "decision_basis_allowed": confidence.get("decision_basis_allowed", True),
        "value": reading.get("value"),
        "unit": reading.get("unit"),
        "trust_reason": confidence.get("trust_reason"),
    }


def _signal_trust_state(confidence: dict | None, reading: dict | None) -> str:
    if confidence and confidence.get("trust_state"):
        return confidence["trust_state"]
    if not reading:
        return "NO_LIVE_SAMPLE"
    if not confidence:
        return "NO_CONFIDENCE_RESULT"
    tier = (confidence or {}).get("tier")
    if tier in ("LOW", "CRITICAL", "MEDIUM"):
        return "DEGRADED"
    return "TRUSTED"


def _mutation_receipt_lines(build_context: dict) -> list[str]:
    mutations = build_context.get("template_mutations", {}) if build_context else {}
    if mutations.get("require_manual_verification_when_level_quarantined"):
        return ["Template mutation active: require manual verification when primary level is quarantined."]
    return []


def _alarm_collapse_receipt(incident: dict) -> dict:
    collapse = incident.get("alarm_collapse") or {}
    raw_signals = collapse.get("raw_signals") or incident.get("affected_sensors") or []
    raw_count = collapse.get("raw_signal_count") or len(raw_signals)
    return {
        "raw_signal_count": raw_count,
        "suppressed_alarm_count": collapse.get("suppressed_alarm_count", max(0, raw_count - 1)),
        "operator_question": collapse.get("operator_question", "Can the operator trust the primary indication before changing the operating rate?"),
        "collapse_reason": collapse.get("collapse_reason", "All signals affect the same operating basis."),
        "raw_signals": raw_signals,
        "consumed_alarm_types": collapse.get("consumed_alarm_types", []),
    }


def _decision_time_score(incident: dict, confidence: list[dict]) -> dict:
    affected = set(incident.get("affected_sensors") or [])
    collapse = _alarm_collapse_receipt(incident)
    contract = incident.get("action_contract") or {}
    blocked_decision_count = len(contract.get("blocked_decisions", []) or incident.get("blocked_decisions", []) or [])
    evidence_count = len(incident.get("evidence_refs", []) or [])
    raw_signal_count = int(collapse.get("raw_signal_count") or len(affected) or 1)
    required_operator_action_count = 1 if (contract.get("operator_single_safe_move") or contract.get("first_safe_action") or incident.get("first_action")) else 0
    collapsed_situation_count = 1 if incident else 0
    traditional_steps = max(1, raw_signal_count + blocked_decision_count + evidence_count)
    confidenceos_steps = max(1, collapsed_situation_count + required_operator_action_count)
    scores = [
        float(item.get("confidence_pct"))
        for item in confidence or []
        if item.get("sensor_id") in affected and item.get("confidence_pct") is not None
    ]
    score = round(sum(scores) / len(scores)) if scores else (35 if incident.get("severity") == "CRITICAL" else 72)
    return {
        "metric_label": "Interaction Compression Estimate",
        "score": score,
        "raw_signal_count": raw_signal_count,
        "suppressed_alarm_count": collapse.get("suppressed_alarm_count", 0),
        "collapsed_situation_count": collapsed_situation_count,
        "blocked_decision_count": blocked_decision_count,
        "required_operator_action_count": required_operator_action_count,
        "traditional_steps": traditional_steps,
        "confidenceos_steps": confidenceos_steps,
        "decision_compression": f"{traditional_steps} -> {confidenceos_steps}",
        "required_operator_actions": required_operator_action_count,
        "method": "Estimated from raw collapsed signals, evidence categories, blocked decisions, collapsed situations, and required operator actions.",
    }
