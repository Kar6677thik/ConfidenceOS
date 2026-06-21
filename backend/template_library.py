"""
template_library.py - Reusable signal/equipment template loading and validation.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from model_graph import equipment_signals, get_assets, get_relationships


BACKEND_DIR = Path(__file__).parent
EQUIPMENT_TEMPLATES_PATH = BACKEND_DIR / "equipment_templates.json"
SIGNAL_TEMPLATES_PATH = BACKEND_DIR / "signal_templates.json"
ROLE_POLICIES_PATH = BACKEND_DIR / "role_policies.json"
CONTEXT_POLICIES_PATH = BACKEND_DIR / "context_policies.json"


@lru_cache(maxsize=1)
def load_equipment_templates() -> dict:
    return _load_json(EQUIPMENT_TEMPLATES_PATH)


@lru_cache(maxsize=1)
def load_signal_templates() -> dict:
    return _load_json(SIGNAL_TEMPLATES_PATH)


@lru_cache(maxsize=1)
def load_role_policies() -> dict:
    return _load_json(ROLE_POLICIES_PATH)


@lru_cache(maxsize=1)
def load_context_policies() -> dict:
    return _load_json(CONTEXT_POLICIES_PATH)


def get_template_catalog() -> dict:
    return {
        "equipment_templates": load_equipment_templates().get("templates", []),
        "signal_templates": load_signal_templates().get("templates", []),
        "role_policies": load_role_policies().get("policies", {}),
        "context_policies": load_context_policies().get("policies", {}),
    }


def template_by_id(template_id: str) -> dict:
    for template in load_equipment_templates().get("templates", []):
        if template.get("template_id") == template_id:
            return template
    return {}


def validate_assignments(assignments: list[dict], model_key: str | None = None) -> dict:
    info = []
    warnings = []
    blocking = []
    valid = []
    assignment_by_asset = {
        item.get("asset_id"): item.get("template_id")
        for item in assignments or []
        if item.get("asset_id") and item.get("template_id")
    }
    assets = get_assets(model_key=model_key)

    for asset in assets:
        asset_id = asset.get("asset_id")
        template_id = assignment_by_asset.get(asset_id) or asset.get("template_id")
        template = template_by_id(template_id)
        if not template or not asset_id:
            continue
        signals = equipment_signals(asset_id, model_key=model_key)
        present_types = {signal.get("sensor_type") for signal in signals}
        missing = [
            signal_type for signal_type in template.get("required_signal_types", [])
            if signal_type not in present_types
        ]
        asset_info = []
        asset_warnings = []
        asset_blocking = []

        _apply_guardrails(
            asset=asset,
            template=template,
            signals=signals,
            present_types=present_types,
            info=asset_info,
            warnings=asset_warnings,
            blocking=asset_blocking,
            model_key=model_key,
        )
        row = {
            "asset_id": asset_id,
            "asset_name": asset.get("name"),
            "template_id": template_id,
            "required_signal_types": template.get("required_signal_types", []),
            "present_signal_types": sorted([item for item in present_types if item]),
            "missing_signal_types": missing,
            "status": "blocking" if asset_blocking else ("warning" if missing or asset_warnings else "valid"),
            "info": asset_info,
            "warnings": asset_warnings,
            "blocking": asset_blocking,
        }
        valid.append(row)
        info.extend(asset_info)
        warnings.extend(asset_warnings)
        blocking.extend(asset_blocking)
        blocking_missing = {
            item.get("signal_type")
            for item in asset_blocking
            if item.get("rule") in ("vessel_primary_level_required", "vessel_requires_at_least_one_flow")
        }
        for signal_type in missing:
            if signal_type in blocking_missing:
                continue
            warnings.append({
                "asset_id": asset_id,
                "template_id": template_id,
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "required_signal_missing_warning",
                "signal_type": signal_type,
                "message": f"{asset_id} template {template_id} is missing required {signal_type} signal.",
            })

    return {
        "status": "blocking" if blocking else ("warnings" if warnings else "valid"),
        "info": info,
        "warnings": warnings,
        "blocking": blocking,
        "items": valid,
        "count": len(info) + len(warnings) + len(blocking),
    }


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _apply_guardrails(
    asset: dict,
    template: dict,
    signals: list[dict],
    present_types: set,
    info: list[dict],
    warnings: list[dict],
    blocking: list[dict],
    model_key: str | None = None,
) -> None:
    asset_id = asset.get("asset_id")
    template_id = template.get("template_id")
    source = {
        "asset_id": asset_id,
        "template_id": template_id,
    }
    if not asset_id or not template_id:
        return

    info.append({
        **source,
        "severity": "INFO",
        "level": "INFO",
        "rule": "template_assignment_visible",
        "message": f"{asset_id} is bound to {template_id}; validation is visible in Studio and Runtime provenance.",
    })

    if template_id == "vessel":
        if "level" not in present_types or not _has_role(signals, "primary_level"):
            blocking.append({
                **source,
                "severity": "BLOCKING",
                "level": "BLOCKING",
                "rule": "vessel_primary_level_required",
                "signal_type": "level",
                "message": f"{asset_id} vessel template is missing a primary level signal.",
            })
        if "flow_in" not in present_types and "flow_out" not in present_types:
            blocking.append({
                **source,
                "severity": "BLOCKING",
                "level": "BLOCKING",
                "rule": "vessel_requires_at_least_one_flow",
                "signal_type": "flow_in/flow_out",
                "message": f"{asset_id} vessel template is missing both inflow and outflow signals.",
            })
        if not _has_role(signals, "independent_high_level_reference"):
            warnings.append({
                **source,
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "independent_high_level_reference_missing",
                "message": f"{asset_id} has no independent high-level reference; publish is allowed but verification wording is required.",
            })
        if any(signal.get("criticality") == "safety_critical" for signal in signals):
            warnings.append({
                **source,
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "manual_verification_workflow_required",
                "message": f"{asset_id} contains a safety-critical signal; manual verification workflow must remain visible.",
            })

    if template_id == "flow_pair" and not _has_confidence_substitute_wording(template):
        warnings.append({
            **source,
            "severity": "WARNING",
            "level": "WARNING",
            "rule": "flow_pair_confidence_substitute_wording_missing",
            "message": f"{asset_id} flow-pair group is missing explicit confidence substitute wording.",
        })

    if template_id == "valve" and "valve" in present_types and not _has_command_signal(signals):
        warnings.append({
            **source,
            "severity": "WARNING",
            "level": "WARNING",
            "rule": "valve_command_signal_missing",
            "message": f"{asset_id} valve template has position feedback but no command signal; publish is allowed for read-only trust monitoring.",
        })

    if template_id == "pump":
        if "vibration" not in present_types:
            warnings.append({
                **source,
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "pump_vibration_signal_missing",
                "signal_type": "vibration",
                "message": f"{asset_id} pump template has no vibration signal; publish is allowed only as a limited device-health faceplate.",
            })
        if ("flow_out" in present_types or "discharge_pressure" in present_types) and not _has_command_signal(signals):
            warnings.append({
                **source,
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "pump_command_signal_missing",
                "message": f"{asset_id} pump template has process evidence but no run/command signal; Runtime will show read-only trust context only.",
            })

    role_visibility = template.get("role_visibility", {})
    maintenance_sections = role_visibility.get("Maintenance", [])
    for signal in signals:
        if signal.get("criticality") != "safety_critical":
            continue
        if not maintenance_sections:
            blocking.append({
                **source,
                "severity": "BLOCKING",
                "level": "BLOCKING",
                "rule": "safety_critical_sensor_requires_maintenance_visibility",
                "sensor_id": signal.get("tag"),
                "message": f"{signal.get('tag')} is safety-critical but {template_id} exposes no Maintenance role visibility.",
            })

    critical_context = load_context_policies().get("policies", {}).get("CRITICAL", {})
    promoted = set(critical_context.get("promoted_sections", []))
    suppressed = set(critical_context.get("suppressed_sections", []))
    evidence_visible = bool(promoted & {"evidence", "evidence_ledger", "confidence_courtroom"})
    if "evidence_ledger" in suppressed or not evidence_visible:
        blocking.append({
            **source,
            "severity": "BLOCKING",
            "level": "BLOCKING",
            "rule": "critical_context_must_not_suppress_evidence",
            "message": "CRITICAL context must keep evidence ledger visible; stress mode cannot suppress operating evidence.",
        })

    if template_id in {"vessel", "flow_pair"} and not _has_mass_balance_relationship(model_key=model_key):
        warnings.append({
            **source,
            "severity": "WARNING",
            "level": "WARNING",
            "rule": "mass_balance_relationship_missing",
            "message": f"{asset_id} uses {template_id} but no mass-balance validation relationship was found.",
        })


def _has_role(signals: list[dict], role: str) -> bool:
    return any(signal.get("role") == role for signal in signals)


def _has_command_signal(signals: list[dict]) -> bool:
    command_roles = {"command", "command_signal", "valve_command", "controller_output", "run_status", "pump_run_status"}
    return any(signal.get("role") in command_roles or signal.get("sensor_type") in command_roles for signal in signals)


def _has_confidence_substitute_wording(template: dict) -> bool:
    text = " ".join(template.get("first_action_patterns", []) + template.get("generated_ui_sections", []))
    normalized = text.lower().replace("_", " ")
    return "trusted substitute" in normalized or "confidence substitute" in normalized


def _has_mass_balance_relationship(model_key: str | None = None) -> bool:
    return any(rel.get("type") == "mass_balance_validation" for rel in get_relationships(model_key=model_key))
