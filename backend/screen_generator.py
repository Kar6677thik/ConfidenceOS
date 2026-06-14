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
) -> dict:
    live_state = live_state or {}
    context_state = _resolve_context(context, live_state)
    role_policy = load_role_policies().get("policies", {}).get(role) or load_role_policies().get("policies", {}).get("Operator", {})
    context_policy = load_context_policies().get("policies", {}).get(context_state, {})
    validation = validate_assignments(assignments or [])
    assets = get_assets()
    faceplates = [
        _faceplate_for_asset(asset, live_state, role, context_state, assignments or [])
        for asset in assets
        if asset.get("asset_type") in ("process_vessel", "valve", "flow_pair")
    ]
    faceplates = [item for item in faceplates if item]
    situations = _situations(live_state)
    stress = _is_stress(live_state, context_state)

    return {
        "manifest_id": f"runtime:{role}:{context_state}",
        "route": "/runtime",
        "generated_at": time.time(),
        "role": role,
        "context": context_state,
        "stress_mode": stress,
        "source": "asset_model_and_template_library",
        "read_only_trust_layer": True,
        "navigation": get_navigation(),
        "role_policy": role_policy,
        "context_policy": context_policy,
        "validation": validation,
        "semantic_zoom": ["plant", "area", "unit", "module", "equipment", "signal"],
        "provenance": {
            "asset_model_id": get_model_graph().get("model_id"),
            "role_policy": role,
            "context_policy": context_state,
            "template_assignments": assignments or [],
        },
        "screens": [
            {
                "screen_id": "plant-overview",
                "screen_type": "plant_overview",
                "title": "Instrument Integrity Overview",
                "sections": ["semantic_navigation", "trust_hotspots", "unresolved_situations"],
            },
            {
                "screen_id": "unit-15-runtime",
                "screen_type": "unit_overview",
                "title": "Unit 15 ISOM Runtime",
                "sections": ["situation_workspace", "generated_faceplates", "shift_channel"],
            },
        ],
        "faceplates": faceplates,
        "situations": situations,
        "operating_basis": _operating_basis(live_state, situations),
        "role_sections": _role_sections(role, live_state),
    }


def equipment_manifest(equipment_id: str, role: str, live_state: dict | None = None, assignments: list[dict] | None = None) -> dict:
    asset = next((item for item in get_assets() if item.get("asset_id") == equipment_id), None)
    if not asset:
        return {}
    return _faceplate_for_asset(asset, live_state or {}, role, "auto", assignments or [])


def _faceplate_for_asset(asset: dict, live_state: dict, role: str, context_state: str, assignments: list[dict]) -> dict:
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
    return {
        "equipment_id": asset_id,
        "title": asset.get("name", asset_id),
        "asset_type": asset.get("asset_type"),
        "template_id": template_id,
        "template_label": template.get("label"),
        "role": role,
        "context": context_state,
        "sections": template.get("role_visibility", {}).get(role, template.get("generated_ui_sections", [])),
        "signals": signal_rows,
        "provenance": {
            "generated_from": ["asset_model.json", "equipment_templates.json", "role_policies.json", "context_policies.json"],
            "template_id": template_id,
            "asset_id": asset_id,
            "approved": assignment.get("approved", False),
        },
    }


def _resolve_context(context: str, live_state: dict) -> str:
    if context and context != "auto":
        return context
    plant_context = live_state.get("plant_context") or {}
    inferred = live_state.get("mode", {}).get("inferred_mode")
    return plant_context.get("state") or inferred or "STEADY_STATE"


def _situations(live_state: dict) -> list[dict]:
    incidents = live_state.get("incidents") or []
    if incidents:
        return incidents
    return []


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


def _role_sections(role: str, live_state: dict) -> list[dict]:
    if role == "Maintenance":
        return [
            {"section": "verification_tokens", "items": live_state.get("verification_tokens", [])},
            {"section": "confidence_debt", "items": live_state.get("confidence_debt", [])},
        ]
    if role == "Engineer":
        return [
            {"section": "signal_mapping", "items": get_model_graph().get("signals", [])},
            {"section": "validation", "items": []},
        ]
    if role in ("Manager", "Auditor"):
        return [
            {"section": "handover_debt", "items": (live_state.get("handover_debt") or {}).get("entries", [])},
            {"section": "timeline", "items": live_state.get("incident_timeline", [])},
        ]
    return [{"section": "operator_basis", "items": [_operating_basis(live_state, _situations(live_state))]}]


def _is_stress(live_state: dict, context_state: str) -> bool:
    severity = (live_state.get("plant_context") or {}).get("severity")
    return severity in ("WARNING", "CRITICAL") or context_state in ("MASS_BALANCE_DIVERGENCE", "MANUAL_VERIFICATION_REQUIRED")
