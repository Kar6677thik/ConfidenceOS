"""
studio_service.py - Lightweight low-code Studio state and deterministic mapping.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from hmi_compiler import imported_tag_buckets, mapping_court, mapping_court_for_tag, run_build
from asset_model import available_asset_models, set_active_asset_model
from hmi_compiler import load_imported_tags
from model_graph import equipment_signals, get_assets, get_model_graph, get_signals
from screen_generator import generate_screen_manifest
from template_library import get_template_catalog, validate_assignments
from template_tests import run_template_tests
from database import (
    SessionLocal,
    list_hmi_build_artifacts,
    list_import_batches,
    mark_hmi_build_published,
    record_hmi_build_artifact,
    record_import_batch,
)
import ai_mapping as _ai


STATE_PATH = Path(__file__).with_name("studio_state.json")


DEFAULT_ASSIGNMENTS = [
    {"asset_id": "V-5100", "template_id": "vessel", "approved": True, "source": "demo_default"},
    {"asset_id": "XV-6100", "template_id": "valve", "approved": True, "source": "demo_default"},
    {"asset_id": "FG-2010", "template_id": "flow_pair", "approved": True, "source": "demo_default"},
]

MODEL_ASSIGNMENTS = {
    "texas_city_vessel": DEFAULT_ASSIGNMENTS,
    "pump_station": [
        {"asset_id": "TK-100", "template_id": "vessel", "approved": True, "source": "demo_default"},
        {"asset_id": "P-101", "template_id": "pump", "approved": True, "source": "demo_default"},
        {"asset_id": "FG-100", "template_id": "flow_pair", "approved": True, "source": "demo_default"},
    ],
}

DEFAULT_APPROVED_BINDINGS = [
    {"raw_tag": "U15_LT_5100.PV", "source": "demo_default_engineer_approval"},
    {"raw_tag": "15-FI-2010", "source": "demo_default_engineer_approval"},
    {"raw_tag": "FO2020_RATE", "source": "demo_default_engineer_approval"},
    {"raw_tag": "ZT6100.POS", "source": "demo_default_engineer_approval"},
    {"raw_tag": "PT_3100_PROCESS", "source": "demo_default_engineer_approval"},
    {"raw_tag": "TEMP4100", "source": "demo_default_engineer_approval"},
]

MODEL_APPROVED_BINDINGS = {
    "texas_city_vessel": DEFAULT_APPROVED_BINDINGS,
    "pump_station": [
        {"raw_tag": "TK100_LIT.PV", "source": "demo_default_engineer_approval"},
        {"raw_tag": "FIT101_FLOW", "source": "demo_default_engineer_approval"},
        {"raw_tag": "FIT102_RATE", "source": "demo_default_engineer_approval"},
        {"raw_tag": "P101_VIB", "source": "demo_default_engineer_approval"},
    ],
}


def get_state() -> dict:
    if not STATE_PATH.exists():
        state = _default_state()
        _activate_state_model(state)
        return state
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state = _with_default_fields(json.load(f))
        _activate_state_model(state)
        return state


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


async def auto_map() -> dict:
    state = get_state()
    court = mapping_court(state)
    suggestions = _asset_mapping_suggestions(court)

    # AI explanation layer — attaches Claude narrative to each court item when key present.
    # Deterministic verdict remains authoritative; AI explains it.
    model_context = _model_context_for_ai(state)
    ai_assisted = False
    ai_label = "deterministic rule active; AI explanation unavailable (no key); engineer approval required"
    items = court.get("items", [])
    if _ai._ai_available() and items:
        enriched = []
        for item in items:
            try:
                explanation = await _ai.explain_mapping(
                    item.get("raw_tag", ""),
                    item,
                    model_context,
                )
                enriched.append({**item, **{
                    "ai_narrative": explanation.get("ai_narrative", ""),
                    "ai_evidence": explanation.get("ai_evidence", []),
                    "ai_counter_evidence": explanation.get("ai_counter_evidence", []),
                    "ai_assisted": explanation.get("ai_assisted", False),
                }})
                if explanation.get("ai_assisted"):
                    ai_assisted = True
            except Exception:
                enriched.append(item)
        court = {**court, "items": enriched}
        if ai_assisted:
            ai_label = "AI explanation active; deterministic rule authoritative; engineer approval required"

    state = get_state()
    state["suggestions"] = suggestions
    save_state(state)
    return {
        "suggestions": suggestions,
        "mapping_court": court,
        "ai_assisted": ai_assisted,
        "ai_label": ai_label,
        "suggestion_labels": court.get("suggestion_labels", {}),
        "approval_required": True,
    }


def manual_map_raw_tag(raw_tag: str, canonical_tag: str, asset_id: str, signal_role: str, reason: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        return {
            "status": "not_mapped",
            "reason": "Manual mapping requires an engineering reason.",
            "mapping": mapping_court_for_tag(raw_tag, get_state()),
        }
    signals = {signal.get("tag"): signal for signal in get_signals()}
    assets = {asset.get("asset_id"): asset for asset in get_assets()}
    signal = signals.get(canonical_tag)
    asset = assets.get(asset_id)
    if not signal or not asset:
        return {
            "status": "not_mapped",
            "reason": "Manual mapping requires a known canonical signal and asset.",
            "mapping": mapping_court_for_tag(raw_tag, get_state()),
        }

    state = get_state()
    approved = [
        item for item in state.get("approved_bindings", [])
        if item.get("raw_tag") != raw_tag
    ]
    approved.append({
        "raw_tag": raw_tag,
        "proposed_canonical_tag": canonical_tag,
        "proposed_asset_id": asset_id,
        "proposed_role": signal_role,
        "sensor_type": signal.get("sensor_type"),
        "unit": signal.get("unit"),
        "template_id": asset.get("template_id"),
        "confidence": 0.72,
        "confidence_band": "ENGINEER_APPROVED",
        "source": "studio_manual_mapping",
        "approved_at": time.time(),
        "evidence": [
            f"Engineer manually bound {raw_tag} to {canonical_tag}.",
            f"Mapped to {asset_id} as {signal_role}.",
            reason,
        ],
        "counter_evidence": ["Manual mapping bypasses deterministic naming confidence and is retained as an engineering receipt."],
        "verdict": "MANUAL_ENGINEER_MAPPING_APPROVED",
    })
    ignored = dict(state.get("ignored_raw_tags", {}))
    ignored.pop(raw_tag, None)
    state["approved_bindings"] = approved
    state["ignored_raw_tags"] = ignored
    state["last_build"] = None
    state["last_build_id"] = None
    save_state(state)
    return {
        "status": "manual_mapped",
        "mapping": mapping_court_for_tag(raw_tag, get_state()),
        "build_invalidated": True,
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
        "template_mutations": state.get("template_mutations", {}),
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


def runtime_manifest(role: str = "Operator", context: str = "auto", live_state: dict | None = None) -> dict:
    """Return Runtime manifest hydrated from the latest published compiler build.

    Runtime remains read-only: this function only joins the approved compiler
    artifact with current simulator/provider state for display.
    """
    state = get_state()
    published = state.get("published_manifest") or {}
    published_build_id = state.get("published_build_id")
    last_build = state.get("last_build") or {}
    build_validation = last_build.get("validation") if last_build.get("build_id") == published_build_id else None
    build_receipts = last_build.get("receipts") if last_build.get("build_id") == published_build_id else None
    build_context = {
        "build_id": published.get("build_id") or published_build_id or "runtime-ad-hoc",
        "validation_status": published.get("validation_status") or last_build.get("status") or "PASS_WITH_WARNINGS",
        "validation": build_validation or published.get("validation") or validate_assignments(state.get("assignments", [])),
        "receipts": build_receipts or published.get("receipts") or published.get("provenance", {}).get("receipts", []),
        "source_tags": published.get("provenance", {}).get("source_tags", []),
        "published_build_id": published_build_id,
        "runtime_source": "published_build" if published else "ad_hoc_generation",
        "template_mutations": state.get("template_mutations", {}),
    }
    manifest = generate_screen_manifest(
        role=role,
        context=context,
        live_state=live_state or {},
        assignments=state.get("assignments", []),
        build_context=build_context,
    )
    return {
        **manifest,
        "published_build_id": published_build_id,
        "published_revision": state.get("published_revision"),
        "runtime_source": build_context["runtime_source"],
    }


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
        _mark_published_build(build.get("build_id"))
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
    default_by_asset = {item["asset_id"]: item for item in _default_assignments_for_model(state.get("selected_asset_model"))}
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
    import_batch_id = _record_current_import_batch(state, build_id)
    build = run_build(state, build_id=build_id)
    build["import_batch_id"] = import_batch_id
    state["last_build_id"] = build_id
    state["last_build"] = build
    state["last_import_batch_id"] = import_batch_id
    save_state(state)
    _record_build_artifact(build, state, import_batch_id)
    return build


def select_asset_model(model_key: str) -> dict:
    state = get_state()
    selected = set_active_asset_model(model_key)
    state["selected_asset_model"] = selected
    state["assignments"] = _default_assignments_for_model(selected)
    state["approved_bindings"] = _default_approved_bindings_for_model(selected)
    state["ignored_raw_tags"] = {}
    state["last_build"] = None
    state["last_build_id"] = None
    state["published_manifest"] = {}
    state["published_build_id"] = None
    save_state(state)
    return studio_overview()


def update_template_mutation(require_manual_verification_when_level_quarantined: bool) -> dict:
    state = get_state()
    state.setdefault("template_mutations", {})["require_manual_verification_when_level_quarantined"] = bool(require_manual_verification_when_level_quarantined)
    state["last_build"] = None
    state["last_build_id"] = None
    save_state(state)
    return {"template_mutations": state["template_mutations"], "state": state}


def template_tests() -> dict:
    return run_template_tests(get_state().get("assignments", []))


def mapping_court_items() -> dict:
    return mapping_court(get_state())


def mapping_court_detail(raw_tag: str) -> dict:
    return mapping_court_for_tag(raw_tag, get_state())


def approve_raw_tag(raw_tag: str) -> dict:
    state = get_state()
    row = mapping_court_for_tag(raw_tag, state)
    if not row.get("proposed_canonical_tag"):
        return {
            "status": "not_approved",
            "reason": "No canonical mapping exists. Mark ignored with a reason or keep blocking.",
            "mapping": row,
        }
    approved = [
        item for item in state.get("approved_bindings", [])
        if item.get("raw_tag") != raw_tag
    ]
    approved.append({
        "raw_tag": raw_tag,
        "source": "studio_engineer_approval",
        "approved_at": time.time(),
    })
    ignored = dict(state.get("ignored_raw_tags", {}))
    ignored.pop(raw_tag, None)
    state["approved_bindings"] = approved
    state["ignored_raw_tags"] = ignored
    state["last_build"] = None
    state["last_build_id"] = None
    save_state(state)
    return {"status": "approved", "mapping": mapping_court_for_tag(raw_tag, get_state())}


def ignore_raw_tag(raw_tag: str, reason: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        return {
            "status": "not_ignored",
            "reason": "Ignored raw tags require an engineering reason.",
            "mapping": mapping_court_for_tag(raw_tag, get_state()),
        }
    state = get_state()
    approved = [
        item for item in state.get("approved_bindings", [])
        if item.get("raw_tag") != raw_tag
    ]
    ignored = dict(state.get("ignored_raw_tags", {}))
    ignored[raw_tag] = reason
    state["approved_bindings"] = approved
    state["ignored_raw_tags"] = ignored
    state["last_build"] = None
    state["last_build_id"] = None
    save_state(state)
    return {"status": "ignored", "mapping": mapping_court_for_tag(raw_tag, get_state())}


def keep_raw_tag_blocking(raw_tag: str) -> dict:
    state = get_state()
    state["approved_bindings"] = [
        item for item in state.get("approved_bindings", [])
        if item.get("raw_tag") != raw_tag
    ]
    ignored = dict(state.get("ignored_raw_tags", {}))
    ignored.pop(raw_tag, None)
    state["ignored_raw_tags"] = ignored
    state["last_build"] = None
    state["last_build_id"] = None
    save_state(state)
    return {"status": "blocking", "mapping": mapping_court_for_tag(raw_tag, get_state())}


def studio_overview() -> dict:
    state = get_state()
    return {
        "state": state,
        "asset_models": available_asset_models(),
        "selected_asset_model": state.get("selected_asset_model"),
        "template_mutations": state.get("template_mutations", {}),
        "graph": get_model_graph(),
        "assets": get_assets(),
        "templates": get_template_catalog(),
        "validation": validation(),
        "diff": diff(),
        "build": state.get("last_build"),
        "mapping_court": mapping_court(state),
    }


async def import_arbitrary_tags(raw_tag_list: list[str]) -> dict:
    """
    Accept an arbitrary pasted tag list, route through AI parse → Mapping Court.

    Every proposal is returned for engineer review via the Mapping Court flow.
    Nothing is auto-approved or auto-published.
    """
    state = get_state()
    model_context = _model_context_for_ai(state)
    import_batch_id = f"manual-import-{int(time.time())}"
    _record_import_batch(
        import_batch_id,
        state.get("selected_asset_model"),
        raw_tag_list,
        source="studio_manual_import",
    )
    state["last_import_batch_id"] = import_batch_id
    save_state(state)

    result = await _ai.parse_arbitrary_tags(raw_tag_list, model_context)

    # For each AI-proposed binding, inject it into the court so the engineer
    # can approve/ignore it exactly like a deterministic suggestion.
    proposals = result.get("proposals", [])
    enriched_proposals = []
    for prop in proposals:
        court_item = mapping_court_for_tag(prop["raw_tag"], state)
        enriched_proposals.append({
            **court_item,
            "ai_proposed_canonical_tag": prop.get("proposed_canonical_tag"),
            "ai_proposed_role": prop.get("proposed_role"),
            "ai_confidence_band": prop.get("confidence_band", "UNCERTAIN"),
            "ai_rationale": prop.get("ai_rationale", ""),
            "ai_assisted": result.get("ai_assisted", False),
            "approval_required": True,
            "source": prop.get("source", "ai_parse"),
        })

    return {
        "ai_assisted": result.get("ai_assisted", False),
        "ai_label": result.get("ai_label", ""),
        "proposals": enriched_proposals,
        "unresolved": result.get("unresolved", []),
        "model": result.get("model"),
        "import_batch_id": import_batch_id,
        "approval_required": True,
        "note": "All proposals require engineer approval before publish.",
    }


def persisted_build_artifacts(model_key: str | None = None, limit: int = 20) -> dict:
    db = SessionLocal()
    try:
        return {
            "build_artifacts": list_hmi_build_artifacts(db, model_key=model_key, limit=limit),
            "storage": "sqlite",
            "immutable_receipts": True,
        }
    finally:
        db.close()


def persisted_import_batches(model_key: str | None = None, limit: int = 20) -> dict:
    db = SessionLocal()
    try:
        return {
            "import_batches": list_import_batches(db, model_key=model_key, limit=limit),
            "storage": "sqlite",
        }
    finally:
        db.close()


async def suggest_template_for_asset(asset_description: str) -> dict:
    """
    Given a plain-English asset description, Claude proposes a template from
    the real template library. Compiler validates; engineer approves.
    """
    catalog = get_template_catalog()
    available_templates = [
        {
            "template_id": t.get("template_id"),
            "label": t.get("label", t.get("template_id")),
            "required_signal_roles": t.get("required_signal_roles", []),
        }
        for t in catalog
    ]
    state = get_state()
    signals = get_signals()

    result = await _ai.suggest_template(asset_description, available_templates, signals)

    # Run the compiler validation on the proposed assignment immediately so the
    # UI can show whether the suggestion would block or pass.
    proposed_template = result.get("proposed_template_id")
    validation_preview = None
    if proposed_template:
        trial_assignments = list(state.get("assignments", []))
        trial_assignments.append({
            "asset_id": "__ai_suggestion_preview__",
            "template_id": proposed_template,
            "approved": False,
            "source": "ai_suggestion_preview",
        })
        validation_preview = validate_assignments(trial_assignments)

    return {
        **result,
        "validation_preview": validation_preview,
        "available_templates": [t["template_id"] for t in available_templates],
        "note": "Deterministic template suggestion from real template library; compiler validates; engineer approves.",
    }


def _model_context_for_ai(state: dict) -> dict:
    signals = get_signals()
    assets = get_assets()
    active_model = state.get("selected_asset_model", "texas_city_vessel")
    equipment_label = active_model.replace("_", " ").title()
    return {
        "equipment_id": active_model,
        "equipment_label": equipment_label,
        "canonical_signals": [
            {
                "tag": s.get("tag"),
                "sensor_type": s.get("sensor_type"),
                "role": s.get("role"),
                "unit": s.get("unit", ""),
            }
            for s in signals
        ],
        "assets": [
            {"asset_id": a.get("asset_id"), "name": a.get("name"), "template_id": a.get("template_id")}
            for a in assets
        ],
    }


def _asset_mapping_suggestions(court: dict) -> list[dict]:
    rows = [
        item for item in court.get("items", [])
        if item.get("proposed_canonical_tag") and not item.get("ignored")
    ]
    rows_by_tag = {item.get("proposed_canonical_tag"): item for item in rows}
    suggestions = []
    for asset in get_assets():
        template_id = asset.get("template_id")
        if template_id not in {"vessel", "valve", "pump", "flow_pair"}:
            continue
        signals = equipment_signals(asset.get("asset_id"))
        signal_tags = [signal.get("tag") for signal in signals if signal.get("tag")]
        mapped_rows = [rows_by_tag[tag] for tag in signal_tags if tag in rows_by_tag]
        confidence_values = [float(row.get("confidence") or 0) for row in mapped_rows]
        confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.62
        missing = [tag for tag in signal_tags if tag not in rows_by_tag]
        evidence = [
            f"{len(mapped_rows)} imported tag(s) bind to {asset.get('asset_id')} through the active asset model.",
            f"{asset.get('asset_id')} is assigned reusable template {template_id}.",
        ]
        if signal_tags:
            evidence.append(f"Modeled source signals: {', '.join(signal_tags)}.")
        counter_evidence = []
        if missing:
            counter_evidence.append(f"No dirty-import mapping was found for: {', '.join(missing)}.")
        if template_id in {"valve", "pump"} and not any(_looks_like_command(tag) for tag in signal_tags):
            counter_evidence.append("No separate command/run-status signal is present in the imported tag set.")
        suggestions.append({
            "asset_id": asset.get("asset_id"),
            "asset_name": asset.get("name"),
            "template_id": template_id,
            "confidence": confidence,
            "confidence_band": _confidence_band(confidence),
            "source": "deterministic_rule",
            "suggestion_type": "deterministic_rule",
            "requires_approval": True,
            "approval_required": True,
            "reason": f"Active asset model binds {len(signal_tags)} signal(s) to {asset.get('asset_id')}.",
            "signal_tags": signal_tags,
            "suggestion_label": "deterministic rule active",
            "ai_suggestion": "AI suggestion optional",
            "approval_label": "engineer approval required",
            "evidence": evidence,
            "counter_evidence": counter_evidence,
            "verdict": "APPROVE_WITH_REVIEW" if counter_evidence else "APPROVE_TEMPLATE_BINDING",
        })
    return suggestions


def _confidence_band(confidence: float) -> str:
    if confidence >= 0.85:
        return "HIGH_DETERMINISTIC_MATCH"
    if confidence >= 0.65:
        return "ENGINEER_REVIEW_RECOMMENDED"
    return "LOW_MAPPING_COVERAGE"


def _looks_like_command(tag: str) -> bool:
    normalized = re.sub(r"[^A-Z0-9]", "", str(tag).upper())
    return any(token in normalized for token in ("CMD", "RUN", "START", "STOP", "MODE"))


def _record_current_import_batch(state: dict, build_id: str) -> str:
    model_key = state.get("selected_asset_model", "texas_city_vessel")
    raw_tags = [item.get("raw_tag") for item in load_imported_tags(model_key).get("tags", []) if item.get("raw_tag")]
    import_batch_id = f"import-{model_key}-{build_id}"
    return _record_import_batch(import_batch_id, model_key, raw_tags, source="imported_tags_demo.json")


def _record_import_batch(import_batch_id: str, model_key: str | None, raw_tags: list[str], source: str) -> str:
    db = SessionLocal()
    try:
        record_import_batch(
            db,
            import_batch_id=import_batch_id,
            model_key=model_key or "texas_city_vessel",
            raw_tags=raw_tags,
            source=source,
        )
    finally:
        db.close()
    return import_batch_id


def _record_build_artifact(build: dict, state: dict, import_batch_id: str | None) -> None:
    db = SessionLocal()
    try:
        record_hmi_build_artifact(
            db,
            build=build,
            model_key=state.get("selected_asset_model", "texas_city_vessel"),
            import_batch_id=import_batch_id,
            state_revision=state.get("revision"),
        )
    finally:
        db.close()


def _mark_published_build(build_id: str | None) -> None:
    if not build_id:
        return
    db = SessionLocal()
    try:
        mark_hmi_build_published(db, build_id)
    finally:
        db.close()


def _default_state() -> dict:
    return {
        "revision": 1,
        "published_revision": 1,
        "last_published_at": None,
        "published_build_id": None,
        "build_counter": 0,
        "last_build_id": None,
        "last_build": None,
        "selected_asset_model": "texas_city_vessel",
        "assignments": _default_assignments_for_model("texas_city_vessel"),
        "template_mutations": {
            "require_manual_verification_when_level_quarantined": False,
        },
        "suggestions": [],
        "approved_bindings": DEFAULT_APPROVED_BINDINGS,
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
    if merged.get("selected_asset_model") not in MODEL_ASSIGNMENTS:
        merged["selected_asset_model"] = "texas_city_vessel"
    if not isinstance(merged.get("template_mutations"), dict):
        merged["template_mutations"] = default["template_mutations"]
    return merged


def _default_assignments_for_model(model_key: str | None) -> list[dict]:
    return [dict(item) for item in MODEL_ASSIGNMENTS.get(model_key or "texas_city_vessel", DEFAULT_ASSIGNMENTS)]


def _default_approved_bindings_for_model(model_key: str | None) -> list[dict]:
    return [dict(item) for item in MODEL_APPROVED_BINDINGS.get(model_key or "texas_city_vessel", DEFAULT_APPROVED_BINDINGS)]


def _activate_state_model(state: dict) -> None:
    set_active_asset_model(state.get("selected_asset_model", "texas_city_vessel"))
