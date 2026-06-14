"""
screen_generator.py - Deterministic generated Runtime screen manifests.
"""

from __future__ import annotations

import time

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
    assets = get_assets()
    faceplates = [
        _faceplate_for_asset(asset, live_state, role, context_state, assignments or [], build_context)
        for asset in assets
        if asset.get("asset_type") in ("process_vessel", "valve", "flow_pair")
    ]
    faceplates = [item for item in faceplates if item]
    situations = _situations(live_state, build_context, role, context_state, validation_status)
    screens = [
        {
            **_generation_metadata(
                build_context=build_context,
                generated_id=f"{build_id}:plant-overview",
                asset_id=plant_id,
                template_id="plant_overview",
                role=role,
                context_state=context_state,
                validation_status=validation_status,
                source_tags=source_tags,
                generated_because=[
                    "Plant overview generated from asset model hierarchy.",
                    "Instrument integrity overview is required for Runtime navigation.",
                ],
                warnings=warnings,
            ),
            "screen_id": "plant-overview",
            "screen_type": "plant_overview",
            "title": "Instrument Integrity Overview",
            "sections": ["semantic_navigation", "trust_hotspots", "unresolved_situations"],
        },
        {
            **_generation_metadata(
                build_context=build_context,
                generated_id=f"{build_id}:unit-15-runtime",
                asset_id="unit-15",
                template_id="unit_overview",
                role=role,
                context_state=context_state,
                validation_status=validation_status,
                source_tags=source_tags,
                generated_because=[
                    "Unit Runtime generated from semantic plant hierarchy.",
                    "Situation workspace and generated faceplates are required for operator use.",
                ],
                warnings=warnings,
            ),
            "screen_id": "unit-15-runtime",
            "screen_type": "unit_overview",
            "title": "Unit 15 ISOM Runtime",
            "sections": ["situation_workspace", "generated_faceplates", "shift_channel"],
        },
    ]
    role_sections = _role_sections(role, live_state, build_context, context_state, validation_status)
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
        "navigation": get_navigation(),
        "role_policy": role_policy,
        "context_policy": context_policy,
        "validation": validation,
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
        "role_sections": role_sections,
        "stress_mode_panel": stress_mode_panel,
    }


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
        signal_rows.append({
            **signal,
            "reading": readings_by_id.get(tag),
            "confidence": confidence_by_id.get(tag),
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
        ],
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
        asset_id = incident.get("asset_id") or "V-5100"
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
                ],
                warnings=_validation_messages(build_context.get("validation", {}), asset_id=asset_id),
            ),
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
        "decision_freeze": contract.get("blocked_decisions", []),
        "exit_condition": contract.get("exit_conditions", []),
        "evidence": lead.get("evidence_refs", []),
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
        rows = [
            {"section": "verification_tokens", "items": live_state.get("verification_tokens", [])},
            {"section": "confidence_debt", "items": live_state.get("confidence_debt", [])},
        ]
    elif role == "Engineer":
        rows = [
            {"section": "signal_mapping", "items": get_model_graph().get("signals", [])},
            {"section": "validation", "items": []},
        ]
    elif role in ("Manager", "Auditor"):
        rows = [
            {"section": "handover_debt", "items": (live_state.get("handover_debt") or {}).get("entries", [])},
            {"section": "timeline", "items": live_state.get("incident_timeline", [])},
        ]
    else:
        rows = [{"section": "operator_basis", "items": [_operating_basis(live_state, _situations(live_state, build_context, role, context_state, validation_status))]}]

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
            ],
            warnings=_validation_messages(build_context.get("validation", {})),
        ),
        "active": active,
        "sections": ["abnormal_situation", "do_not_trust", "trusted_substitute", "first_safe_action", "exit_condition", "evidence"],
        "operating_basis": basis,
    }


def _is_stress(live_state: dict, context_state: str) -> bool:
    severity = (live_state.get("plant_context") or {}).get("severity")
    return severity in ("WARNING", "CRITICAL") or context_state in ("MASS_BALANCE_DIVERGENCE", "MANUAL_VERIFICATION_REQUIRED")


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
