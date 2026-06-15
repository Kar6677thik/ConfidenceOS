"""
hmi_compiler.py - Deterministic HMI Compiler pipeline for ConfidenceOS.

The compiler is intentionally read-only: it builds Runtime manifests and
engineering receipts from imported tags, asset metadata, templates, policies,
and live-state hooks. It never writes process tags or control commands.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from model_graph import get_assets, get_model_graph
from asset_model import active_asset_model_key, mass_balance_validation
from screen_generator import generate_screen_manifest
from template_library import validate_assignments


BACKEND_DIR = Path(__file__).parent
IMPORTED_TAGS_PATH = BACKEND_DIR / "imported_tags_demo.json"

PIPELINE_STAGE_IDS = [
    "import",
    "mapping",
    "template_binding",
    "validation",
    "screen_generation",
    "publish_readiness",
    "runtime",
]

SUGGESTION_LABELS = {
    "suggestion_type": "deterministic rule active",
    "ai_assist": "AI suggestion optional",
    "approval": "engineer approval required",
}


def load_imported_tags() -> dict:
    with open(IMPORTED_TAGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def imported_tag_buckets(state: dict | None = None) -> dict:
    rows = [mapping_court_for_tag(tag["raw_tag"], state=state) for tag in load_imported_tags().get("tags", [])]
    buckets = {
        "mapped": [],
        "ambiguous": [],
        "unmapped": [],
        "ignored": [],
        "blocking": [],
    }
    for row in rows:
        bucket = row.get("bucket", "unmapped")
        buckets.setdefault(bucket, []).append(row)
        if row.get("blocking"):
            buckets["blocking"].append(row)

    return {
        "source": load_imported_tags().get("source"),
        "suggestion_labels": dict(SUGGESTION_LABELS),
        "raw_tags": rows,
        "buckets": buckets,
        "counts": {key: len(value) for key, value in buckets.items()},
    }


def mapping_court(state: dict | None = None) -> dict:
    payload = imported_tag_buckets(state)
    return {
        "source": payload["source"],
        "suggestion_labels": payload["suggestion_labels"],
        "items": payload["raw_tags"],
        "counts": payload["counts"],
    }


def mapping_court_for_tag(raw_tag: str, state: dict | None = None) -> dict:
    tag = _tag_by_raw(raw_tag)
    if not tag:
        return {
            "raw_tag": raw_tag,
            "bucket": "unmapped",
            "blocking": True,
            "suggestion_type": "deterministic_rule",
            "suggestion_label": SUGGESTION_LABELS["suggestion_type"],
            "ai_suggestion": SUGGESTION_LABELS["ai_assist"],
            "approval_required": True,
            "evidence": [],
            "counter_evidence": ["Raw tag was not found in the imported tag list."],
            "verdict": "UNKNOWN_TAG",
        }

    state = state or {}
    approved = _approved_binding(raw_tag, state)
    ignored_reason = _ignored_reason(raw_tag, state)
    effective = deepcopy(tag)
    if approved:
        effective.update({key: value for key, value in approved.items() if value is not None})
        effective["status"] = "mapped"
    elif ignored_reason:
        effective["status"] = "ignored"
        effective["ignore_reason"] = ignored_reason

    status = effective.get("status", "unmapped")
    bucket = status if status in {"mapped", "ambiguous", "ignored"} else "unmapped"
    blocking = bool(effective.get("blocking")) and not approved and not ignored_reason

    return {
        "raw_tag": raw_tag,
        "bucket": bucket,
        "blocking": blocking,
        "proposed_canonical_tag": effective.get("proposed_canonical_tag"),
        "proposed_asset_id": effective.get("proposed_asset_id"),
        "proposed_role": effective.get("proposed_role"),
        "sensor_type": effective.get("sensor_type"),
        "unit": effective.get("unit"),
        "template_id": effective.get("template_id"),
        "confidence": effective.get("confidence", 0.0),
        "suggestion_type": "deterministic_rule",
        "suggestion_label": SUGGESTION_LABELS["suggestion_type"],
        "ai_suggestion": SUGGESTION_LABELS["ai_assist"],
        "approval_required": status != "ignored",
        "approval_label": SUGGESTION_LABELS["approval"],
        "approved": bool(approved),
        "ignored": bucket == "ignored",
        "ignore_reason": effective.get("ignore_reason"),
        "evidence": list(effective.get("evidence", [])),
        "counter_evidence": list(effective.get("counter_evidence", [])),
        "verdict": effective.get("verdict", "REVIEW_REQUIRED"),
    }


def run_build(
    state: dict | None = None,
    build_id: str = "hmi-build-0001",
    live_state: dict | None = None,
) -> dict:
    state = state or {}
    assignments = state.get("assignments", [])
    mapping_payload = mapping_court(state)
    validation = _build_validation(mapping_payload, assignments)
    blocking = validation["blocking"]
    warnings = validation["warnings"]
    receipts = _build_receipts(mapping_payload, validation)

    generated_manifest: dict[str, Any] = {}
    if not blocking:
        manifest_validation_status = "PASS_WITH_WARNINGS" if warnings else "PASS"
        generated_manifest = generate_screen_manifest(
            role="Operator",
            context="auto",
            live_state=live_state or {},
            assignments=assignments,
            build_context={
                "build_id": build_id,
                "validation_status": manifest_validation_status,
                "validation": validation,
                "receipts": receipts,
                "source_tags": _source_tags(mapping_payload),
                "template_mutations": state.get("template_mutations", {}),
                "active_asset_model": state.get("selected_asset_model") or active_asset_model_key(),
            },
        )
        receipts.append(_receipt(
            "screen_generation",
            "INFO",
            "Generated Runtime manifest from approved asset model, templates, and signal binding.",
            build_id=build_id,
        ))

    can_publish = not blocking
    status = "FAILED" if blocking else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    publish_diff = _publish_diff(generated_manifest, validation, can_publish, state.get("template_mutations", {}))

    return {
        "build_id": build_id,
        "status": status,
        "can_publish": can_publish,
        "read_only_trust_layer": True,
        "pipeline": "Raw Tags -> Asset Graph -> Template Binding -> Validation -> Screen Generation -> Publish Readiness -> Runtime",
        "suggestion_labels": dict(SUGGESTION_LABELS),
        "active_asset_model": state.get("selected_asset_model") or active_asset_model_key(),
        "template_mutations": state.get("template_mutations", {}),
        "stages": _stages(mapping_payload, validation, generated_manifest, can_publish),
        "validation": validation,
        "imported_tags": mapping_payload,
        "asset_graph": get_model_graph(),
        "generated_manifest": generated_manifest,
        "publish_diff": publish_diff,
        "receipts": receipts,
    }


def _build_validation(mapping_payload: dict, assignments: list[dict]) -> dict:
    info = []
    warnings = []
    blocking = []

    for item in mapping_payload.get("items", []):
        raw_tag = item.get("raw_tag")
        if item.get("ignored"):
            info.append({
                "severity": "INFO",
                "level": "INFO",
                "rule": "dirty_raw_tag_ignored",
                "raw_tag": raw_tag,
                "message": f"{raw_tag} ignored: {item.get('ignore_reason') or 'not bound to Runtime'}.",
            })
        elif item.get("blocking"):
            blocking.append({
                "severity": "BLOCKING",
                "level": "BLOCKING",
                "rule": "dirty_raw_tag_unresolved",
                "raw_tag": raw_tag,
                "message": f"{raw_tag} is unresolved and must be mapped or ignored with a reason before publish.",
            })
        elif _maps_to_critical_asset_without_approval(item):
            blocking.append({
                "severity": "BLOCKING",
                "level": "BLOCKING",
                "rule": "dirty_critical_mapping_requires_engineer_approval",
                "raw_tag": raw_tag,
                "asset_id": item.get("proposed_asset_id"),
                "message": f"{raw_tag} maps to critical asset {item.get('proposed_asset_id')} and requires engineer approval before publish.",
            })
        elif item.get("bucket") == "ambiguous":
            warnings.append({
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "dirty_raw_tag_ambiguous",
                "raw_tag": raw_tag,
                "message": f"{raw_tag} has an ambiguous deterministic mapping and should be engineer-reviewed.",
            })
        elif item.get("approval_required") and not item.get("approved"):
            warnings.append({
                "severity": "WARNING",
                "level": "WARNING",
                "rule": "dirty_raw_tag_approval_recommended",
                "raw_tag": raw_tag,
                "message": f"{raw_tag} uses deterministic suggestion; engineer approval is required for final commissioning.",
            })

    template_validation = validate_assignments(assignments)
    info.extend(template_validation.get("info", []))
    warnings.extend(template_validation.get("warnings", []))
    blocking.extend(template_validation.get("blocking", []))

    return {
        "status": "BLOCKING" if blocking else ("WARNING" if warnings else "PASS"),
        "info": info,
        "warnings": warnings,
        "blocking": blocking,
        "items": template_validation.get("items", []),
        "count": len(info) + len(warnings) + len(blocking),
    }


def _stages(mapping_payload: dict, validation: dict, generated_manifest: dict, can_publish: bool) -> list[dict]:
    has_mapping_warning = bool(
        mapping_payload.get("counts", {}).get("ambiguous")
        or mapping_payload.get("counts", {}).get("unmapped")
        or validation.get("warnings")
    )
    has_blocking = bool(validation.get("blocking"))
    return [
        {"id": "import", "label": "Raw Tags", "status": "PASS"},
        {"id": "mapping", "label": "Asset Graph", "status": "WARNING" if has_mapping_warning else "PASS"},
        {"id": "template_binding", "label": "Template Binding", "status": "PASS"},
        {"id": "validation", "label": "Validation", "status": "BLOCKING" if has_blocking else ("WARNING" if validation.get("warnings") else "PASS")},
        {"id": "screen_generation", "label": "Screen Generation", "status": "PASS" if generated_manifest else "NOT_RUN"},
        {"id": "publish_readiness", "label": "Publish Readiness", "status": "PASS" if can_publish else "BLOCKED"},
        {"id": "runtime", "label": "Runtime", "status": "READY" if can_publish else "NOT_READY"},
    ]


def _build_receipts(mapping_payload: dict, validation: dict) -> list[dict]:
    receipts = []
    for item in mapping_payload.get("items", []):
        severity = "INFO"
        if item.get("blocking"):
            severity = "BLOCKING"
        elif item.get("bucket") == "ambiguous" or (item.get("approval_required") and not item.get("approved")):
            severity = "WARNING"
        receipts.append(_receipt(
            "mapping",
            severity,
            f"{item.get('raw_tag')} -> {item.get('proposed_canonical_tag') or 'unmapped'}",
            raw_tag=item.get("raw_tag"),
            canonical_tag=item.get("proposed_canonical_tag"),
            verdict=item.get("verdict"),
            evidence=item.get("evidence", []),
            counter_evidence=item.get("counter_evidence", []),
        ))
    for entry in validation.get("info", []) + validation.get("warnings", []) + validation.get("blocking", []):
        receipts.append(_receipt(
            "validation",
            entry.get("severity", "INFO"),
            entry.get("message", "Validation event."),
            raw_tag=entry.get("raw_tag"),
            asset_id=entry.get("asset_id"),
        ))
    return receipts


def _publish_diff(generated_manifest: dict, validation: dict, can_publish: bool, template_mutations: dict | None = None) -> dict:
    blocking = validation.get("blocking", [])
    warnings = validation.get("warnings", [])
    if not can_publish:
        changes = _blocked_diff_items(blocking, warnings)
        return {
            "status": "blocked",
            "changes": changes,
            "blocked": blocking,
            "warnings": warnings,
            "change_count": len(changes),
        }
    faceplates = generated_manifest.get("faceplates", [])
    screens = generated_manifest.get("screens", [])
    changes = [
        {"type": "generated_screen", "id": screen.get("screen_id"), "title": screen.get("title")}
        for screen in screens
    ]
    changes.extend([
        {"type": "generated_faceplate", "equipment_id": item.get("equipment_id"), "template_id": item.get("template_id")}
        for item in faceplates
    ])
    changes.extend(_semantic_generation_diff(generated_manifest, validation, template_mutations or {}))
    return {
        "status": "ready",
        "changes": changes,
        "blocked": blocking,
        "warnings": warnings,
        "change_count": len(changes),
    }


def _source_tags(mapping_payload: dict) -> list[str]:
    tags = [
        item.get("proposed_canonical_tag")
        for item in mapping_payload.get("items", [])
        if item.get("proposed_canonical_tag") and not item.get("ignored")
    ]
    return sorted(set(tags))


def _tag_by_raw(raw_tag: str) -> dict | None:
    for tag in load_imported_tags().get("tags", []):
        if tag.get("raw_tag") == raw_tag:
            return tag
    return None


def _approved_binding(raw_tag: str, state: dict) -> dict | None:
    for item in state.get("approved_bindings", []):
        if item.get("raw_tag") == raw_tag:
            return item
    return None


def _ignored_reason(raw_tag: str, state: dict) -> str | None:
    ignored = state.get("ignored_raw_tags", {})
    reason = ignored.get(raw_tag)
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return None


def _maps_to_critical_asset_without_approval(item: dict) -> bool:
    if item.get("approved") or item.get("ignored"):
        return False
    if item.get("bucket") not in {"mapped", "ambiguous"}:
        return False
    asset_id = item.get("proposed_asset_id")
    if not asset_id:
        return False
    criticality_by_asset = {
        asset.get("asset_id"): asset.get("criticality")
        for asset in get_assets()
    }
    return criticality_by_asset.get(asset_id) in {"high", "critical", "safety_critical"}


def _blocked_diff_items(blocking: list[dict], warnings: list[dict]) -> list[dict]:
    changes = []
    for item in blocking:
        changes.append({
            "type": "publish_blocked",
            "rule": item.get("rule"),
            "asset_id": item.get("asset_id"),
            "raw_tag": item.get("raw_tag"),
            "description": item.get("message"),
        })
    for item in warnings:
        if item.get("rule") == "valve_command_signal_missing":
            changes.append({
                "type": "publish_warning",
                "rule": item.get("rule"),
                "asset_id": item.get("asset_id"),
                "description": "Valve template has position feedback but no command signal; demo publish remains allowed after BLOCKING items are cleared.",
            })
    return changes


def _semantic_generation_diff(generated_manifest: dict, validation: dict, template_mutations: dict) -> list[dict]:
    changes = []
    faceplates = generated_manifest.get("faceplates", [])
    by_template = {item.get("template_id"): item for item in faceplates}
    vessel = by_template.get("vessel")
    if vessel:
        changes.append({
            "type": "generated_hmi_change",
            "asset_id": vessel.get("equipment_id"),
            "description": f"Added vessel faceplate for {vessel.get('equipment_id')}.",
        })
        signal_tags = {signal.get("tag") for signal in vessel.get("signals", [])}
        relationship = mass_balance_validation()
        required_tags = set(relationship.get("source_tags", []) + [relationship.get("validated_tag")])
        if required_tags and required_tags.issubset(signal_tags):
            changes.append({
                "type": "generated_hmi_change",
                "asset_id": vessel.get("equipment_id"),
                "description": f"Added mass-balance section because {', '.join(relationship.get('source_tags', []))} validate {relationship.get('validated_tag')}.",
            })
            changes.append({
                "type": "generated_hmi_change",
                "asset_id": vessel.get("equipment_id"),
                "decision_id": "operating_basis_decision",
                "description": "Added decision freeze rule from asset-model affected decisions.",
            })
            changes.append({
                "type": "generated_hmi_change",
                "asset_id": vessel.get("equipment_id"),
                "sensor_id": relationship.get("validated_tag"),
                "description": f"Added Maintenance verification task for {relationship.get('validated_tag')}.",
            })
    if template_mutations.get("require_manual_verification_when_level_quarantined"):
        changes.extend([
            {
                "type": "template_mutation_effect",
                "description": "Operator stress mode includes verification-required panel.",
            },
            {
                "type": "template_mutation_effect",
                "description": "Maintenance view receives field verification task.",
            },
            {
                "type": "template_mutation_effect",
                "description": "Handover channel pins unresolved verification.",
            },
            {
                "type": "template_mutation_effect",
                "description": "Runtime receipt references the template mutation.",
            },
        ])
    for warning in validation.get("warnings", []):
        if warning.get("rule") == "valve_command_signal_missing":
            changes.append({
                "type": "generated_hmi_warning",
                "asset_id": warning.get("asset_id"),
                "description": warning.get("message"),
            })
    return changes


def _receipt(stage: str, severity: str, message: str, **extra) -> dict:
    return {
        "stage": stage,
        "severity": severity,
        "message": message,
        **{key: value for key, value in extra.items() if value is not None},
    }
