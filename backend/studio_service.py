"""
studio_service.py - Lightweight low-code Studio state and deterministic mapping.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from model_graph import get_assets, get_model_graph, get_signals
from screen_generator import generate_screen_manifest
from template_library import get_template_catalog, validate_assignments


STATE_PATH = Path(__file__).with_name("studio_state.json")


DEFAULT_ASSIGNMENTS = [
    {"asset_id": "V-5100", "template_id": "vessel", "approved": True, "source": "demo_default"},
    {"asset_id": "XV-6100", "template_id": "valve", "approved": True, "source": "demo_default"},
    {"asset_id": "FG-2010", "template_id": "flow_pair", "approved": True, "source": "demo_default"},
]


def get_state() -> dict:
    if not STATE_PATH.exists():
        return _default_state()
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> dict:
    state["revision"] = int(state.get("revision", 0)) + 1
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


def imported_signals() -> dict:
    signals = get_signals()
    return {
        "source": "SimulatorProvider + asset_model.json",
        "signals": signals,
        "mapped_count": sum(1 for item in signals if item.get("mapped")),
        "unmapped_count": sum(1 for item in signals if not item.get("mapped")),
    }


def auto_map() -> dict:
    suggestions = [
        {
            "asset_id": "V-5100",
            "asset_name": "Raffinate splitter demo vessel",
            "template_id": "vessel",
            "confidence": 0.98,
            "source": "deterministic_rule",
            "requires_approval": True,
            "reason": "Level, inflow, and outflow signals match vessel template requirements.",
            "signal_tags": ["LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100"]
        },
        {
            "asset_id": "XV-6100",
            "asset_name": "Feed control valve",
            "template_id": "valve",
            "confidence": 0.94,
            "source": "deterministic_rule",
            "requires_approval": True,
            "reason": "ZT-6100 valve-position signal matches valve template.",
            "signal_tags": ["ZT-6100"]
        },
        {
            "asset_id": "FG-2010",
            "asset_name": "Feed/outflow balance group",
            "template_id": "flow_pair",
            "confidence": 0.96,
            "source": "deterministic_rule",
            "requires_approval": True,
            "reason": "FI-2010 and FO-2020 form a mass-balance pair.",
            "signal_tags": ["FI-2010", "FO-2020"]
        }
    ]
    state = get_state()
    state["suggestions"] = suggestions
    save_state(state)
    return {"suggestions": suggestions, "ai_assisted": False, "approval_required": True}


def assign_template(asset_id: str, template_id: str, approved: bool = True) -> dict:
    state = get_state()
    assignments = [
        item for item in state.get("assignments", [])
        if item.get("asset_id") != asset_id
    ]
    assignments.append({
        "asset_id": asset_id,
        "template_id": template_id,
        "approved": approved,
        "source": "studio_user",
        "updated_at": time.time(),
    })
    state["assignments"] = assignments
    save_state(state)
    return {"assignment": assignments[-1], "validation": validate_assignments(assignments)}


def generate_preview(role: str = "Engineer", context: str = "auto") -> dict:
    state = get_state()
    manifest = generate_screen_manifest(role=role, context=context, assignments=state.get("assignments", []))
    state["last_generated_manifest_id"] = manifest.get("manifest_id")
    state["last_generated_at"] = manifest.get("generated_at")
    save_state(state)
    return manifest


def publish() -> dict:
    state = get_state()
    validation = validate_assignments(state.get("assignments", []))
    state["published_revision"] = state.get("revision", 1)
    state["last_published_at"] = time.time()
    state["published_manifest"] = generate_screen_manifest(assignments=state.get("assignments", []))
    save_state(state)
    return {
        "status": "published",
        "published_revision": state["published_revision"],
        "validation": validation,
        "read_only_trust_layer": True,
    }


def reset() -> dict:
    state = _default_state()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


def validation() -> dict:
    return validate_assignments(get_state().get("assignments", []))


def diff() -> dict:
    state = get_state()
    current = state.get("assignments", [])
    default_by_asset = {item["asset_id"]: item for item in DEFAULT_ASSIGNMENTS}
    current_by_asset = {item["asset_id"]: item for item in current}
    changes = []
    for asset_id, item in current_by_asset.items():
        default = default_by_asset.get(asset_id)
        if not default:
            changes.append({"type": "added_assignment", "asset_id": asset_id, "current": item})
        elif default.get("template_id") != item.get("template_id"):
            changes.append({"type": "template_changed", "asset_id": asset_id, "from": default.get("template_id"), "to": item.get("template_id")})
    for asset_id, item in default_by_asset.items():
        if asset_id not in current_by_asset:
            changes.append({"type": "removed_assignment", "asset_id": asset_id, "previous": item})
    return {
        "revision": state.get("revision"),
        "published_revision": state.get("published_revision"),
        "changes": changes,
        "change_count": len(changes),
    }


def studio_overview() -> dict:
    return {
        "state": get_state(),
        "graph": get_model_graph(),
        "assets": get_assets(),
        "templates": get_template_catalog(),
        "validation": validation(),
        "diff": diff(),
    }


def _default_state() -> dict:
    return {
        "revision": 1,
        "published_revision": 1,
        "last_published_at": None,
        "assignments": DEFAULT_ASSIGNMENTS,
        "suggestions": [],
        "notes": [],
    }
