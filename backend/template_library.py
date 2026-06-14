"""
template_library.py - Reusable signal/equipment template loading and validation.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from model_graph import equipment_signals, get_assets


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


def validate_assignments(assignments: list[dict]) -> dict:
    warnings = []
    valid = []
    assignment_by_asset = {
        item.get("asset_id"): item.get("template_id")
        for item in assignments or []
        if item.get("asset_id") and item.get("template_id")
    }
    assets = get_assets()

    for asset in assets:
        asset_id = asset.get("asset_id")
        template_id = assignment_by_asset.get(asset_id) or asset.get("template_id")
        template = template_by_id(template_id)
        if not template or not asset_id:
            continue
        signals = equipment_signals(asset_id)
        present_types = {signal.get("sensor_type") for signal in signals}
        missing = [
            signal_type for signal_type in template.get("required_signal_types", [])
            if signal_type not in present_types
        ]
        row = {
            "asset_id": asset_id,
            "asset_name": asset.get("name"),
            "template_id": template_id,
            "required_signal_types": template.get("required_signal_types", []),
            "present_signal_types": sorted([item for item in present_types if item]),
            "missing_signal_types": missing,
            "status": "valid" if not missing else "warning",
        }
        valid.append(row)
        for signal_type in missing:
            warnings.append({
                "asset_id": asset_id,
                "template_id": template_id,
                "severity": "WARNING",
                "message": f"{asset_id} template {template_id} is missing required {signal_type} signal.",
            })

    return {
        "status": "valid" if not warnings else "warnings",
        "warnings": warnings,
        "items": valid,
        "count": len(warnings),
    }


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
