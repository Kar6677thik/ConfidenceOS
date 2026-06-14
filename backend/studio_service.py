"""
studio_service.py - Lightweight low-code Studio state and deterministic mapping.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from hmi_compiler import imported_tag_buckets, mapping_court, mapping_court_for_tag, run_build
from model_graph import get_assets, get_model_graph, get_signals
from screen_generator import generate_screen_manifest
from template_library import get_template_catalog, validate_assignments
from template_tests import run_template_tests


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
        return _with_default_fields(json.load(f))


def save_state(state: dict) -> dict:
    state["revision"] = int(state.get("revision", 0)) + 1
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


def imported_signals() -> dict:
    signals = get_signals()
    dirty_import = imported_tag_buckets(get_state())
    return {
        "source": "SimulatorProvider + asset_model.json",
        "signals": signals,
        "mapped_count": sum(1 for item in signals if item.get("mapped")),
        "unmapped_count": sum(1 for item in signals if not item.get("mapped")),
        "dirty_import": dirty_import,
        "raw_tags": dirty_import.get("raw_tags", []),
        "buckets": dirty_import.get("buckets", {}),
        "counts": dirty_import.get("counts", {}),
    }


def auto_map() -> dict:
    court = mapping_court(get_state())
    suggestions = [
        {
            "asset_id": "V-5100",
            "asset_name": "Raffinate splitter demo vessel",
            "template_id": "vessel",
            "confidence": 0.98,
            "source": "deterministic_rule",
            "requires_approval": True,
            "reason": "Level, inflow, and outflow signals match vessel template requirements.",
            "signal_tags": ["LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100"],
            "suggestion_label": "deterministic rule active",
            "ai_suggestion": "AI suggestion optional",
            "approval_label": "engineer approval required",
            "evidence": [
                "LT/FI/FO imported tags match known vessel signal roles.",
                "Suffixes match Unit 15 demo asset metadata.",
            ],
            "counter_evidence": ["PT_3100_PROCESS remains ambiguous until engineer review."],
            "verdict": "APPROVE_WITH_REVIEW",
        },
        {
            "asset_id": "XV-6100",
            "asset_name": "Feed control valve",
            "template_id": "valve",
            "confidence": 0.94,
            "source": "deterministic_rule",
            "requires_approval": True,
            "reason": "ZT-6100 valve-position signal matches valve template.",
            "signal_tags": ["ZT-6100"],
            "suggestion_label": "deterministic rule active",
            "ai_suggestion": "AI suggestion optional",
            "approval_label": "engineer approval required",
            "evidence": ["ZT6100.POS maps to valve-position feedback for XV-6100."],
            "counter_evidence": ["No separate command tag was imported."],
            "verdict": "APPROVE_WITH_COMMAND_SIGNAL_WARNING",
        },
        {
            "asset_id": "FG-2010",
            "asset_name": "Feed/outflow balance group",
            "template_id": "flow_pair",
            "confidence": 0.96,
            "source": "deterministic_rule",
            "requires_approval": True,
            "reason": "FI-2010 and FO-2020 form a mass-balance pair.",
            "signal_tags": ["FI-2010", "FO-2020"],
            "suggestion_label": "deterministic rule active",
            "ai_suggestion": "AI suggestion optional",
            "approval_label": "engineer approval required",
            "evidence": ["Inlet and outlet flow tags bind to the asset model mass-balance relationship."],
            "counter_evidence": [],
            "verdict": "APPROVE_AS_VALIDATION_PAIR",
        }
    ]
    state = get_state()
    state["suggestions"] = suggestions
    save_state(state)
    return {
        "suggestions": suggestions,
        "mapping_court": court,
        "ai_assisted": False,
        "suggestion_labels": court.get("suggestion_labels", {}),
        "approval_required": True,
    }


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
    build = state.get("last_build") or {}
    build_context = {
        "build_id": build.get("build_id", "studio-preview"),
        "validation_status": build.get("status", "PREVIEW"),
        "receipts": build.get("receipts", []),
        "source_tags": (build.get("generated_manifest") or {}).get("provenance", {}).get("source_tags", []),
    }
    manifest = generate_screen_manifest(
        role=role,
        context=context,
        assignments=state.get("assignments", []),
        build_context=build_context,
    )
    state["last_generated_manifest_id"] = manifest.get("manifest_id")
    state["last_generated_at"] = manifest.get("generated_at")
    save_state(state)
    return manifest


def publish() -> dict:
    state = get_state()
    build = state.get("last_build")
    if build:
        blocking = build.get("validation", {}).get("blocking", [])
        if blocking or not build.get("can_publish"):
            return {
                "status": "blocked",
                "reason": "Compiler validation has BLOCKING issues. Map or explicitly ignore unresolved tags before publish.",
                "build_id": build.get("build_id"),
                "validation": build.get("validation", {}),
                "blocking": blocking,
                "read_only_trust_layer": True,
            }
        state["published_build_id"] = build.get("build_id")
        state["published_revision"] = state.get("revision", 1)
        state["last_published_at"] = time.time()
        state["published_manifest"] = build.get("generated_manifest", {})
        save_state(state)
        return {
            "status": "published",
            "published_build_id": state["published_build_id"],
            "published_revision": state["published_revision"],
            "validation": build.get("validation", {}),
            "publish_diff": build.get("publish_diff", {}),
            "read_only_trust_layer": True,
        }

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
    state = get_state()
    build = state.get("last_build")
    template_validation = validate_assignments(state.get("assignments", []))
    if not build:
        return template_validation
    return {
        **template_validation,
        "compiler": build.get("validation", {}),
        "build_id": build.get("build_id"),
        "can_publish": build.get("can_publish", False),
    }


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
        "published_build_id": state.get("published_build_id"),
        "last_build_id": state.get("last_build_id"),
        "compiler_publish_diff": (state.get("last_build") or {}).get("publish_diff", {}),
        "changes": changes,
        "change_count": len(changes),
    }


def current_build() -> dict:
    state = get_state()
    return state.get("last_build") or run_build(state, build_id="hmi-build-0001")


def run_compiler_build() -> dict:
    state = get_state()
    state["build_counter"] = int(state.get("build_counter", 0)) + 1
    build_id = f"hmi-build-{state['build_counter']:04d}"
    build = run_build(state, build_id=build_id)
    state["last_build_id"] = build_id
    state["last_build"] = build
    save_state(state)
    return build


def template_tests() -> dict:
    return run_template_tests(get_state().get("assignments", []))


def mapping_court_items() -> dict:
    return mapping_court(get_state())


def mapping_court_detail(raw_tag: str) -> dict:
    return mapping_court_for_tag(raw_tag, get_state())


def studio_overview() -> dict:
    state = get_state()
    return {
        "state": state,
        "graph": get_model_graph(),
        "assets": get_assets(),
        "templates": get_template_catalog(),
        "validation": validation(),
        "diff": diff(),
        "build": state.get("last_build"),
        "mapping_court": mapping_court(state),
    }


def _default_state() -> dict:
    return {
        "revision": 1,
        "published_revision": 1,
        "last_published_at": None,
        "published_build_id": None,
        "build_counter": 0,
        "last_build_id": None,
        "last_build": None,
        "assignments": DEFAULT_ASSIGNMENTS,
        "suggestions": [],
        "approved_bindings": [],
        "ignored_raw_tags": {},
        "notes": [],
    }


def _with_default_fields(state: dict) -> dict:
    default = _default_state()
    merged = {**default, **state}
    for key in ("assignments", "suggestions", "notes", "approved_bindings"):
        if not isinstance(merged.get(key), list):
            merged[key] = default[key]
    if not isinstance(merged.get("ignored_raw_tags"), dict):
        merged["ignored_raw_tags"] = {}
    return merged
