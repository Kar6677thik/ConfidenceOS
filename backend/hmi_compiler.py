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

from model_graph import get_model_graph
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
                "receipts": receipts,
                "source_tags": _source_tags(mapping_payload),
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
    publish_diff = _publish_diff(generated_manifest, validation, can_publish)

    return {
        "build_id": build_id,
        "status": status,
        "can_publish": can_publish,
        "read_only_trust_layer": True,
        "pipeline": "Raw Tags -> Asset Graph -> Template Binding -> Validation -> Screen Generation -> Publish Readiness -> Runtime",
        "suggestion_labels": dict(SUGGESTION_LABELS),
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
                "raw_tag": raw_tag,
                "message": f"{raw_tag} ignored: {item.get('ignore_reason') or 'not bound to Runtime'}.",
            })
        elif item.get("blocking"):
            blocking.append({
                "severity": "BLOCKING",
                "raw_tag": raw_tag,
                "message": f"{raw_tag} is unresolved and must be mapped or ignored with a reason before publish.",
            })
        elif item.get("bucket") == "ambiguous":
            warnings.append({
                "severity": "WARNING",
                "raw_tag": raw_tag,
                "message": f"{raw_tag} has an ambiguous deterministic mapping and should be engineer-reviewed.",
            })
        elif item.get("approval_required") and not item.get("approved"):
            warnings.append({
                "severity": "WARNING",
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


def _publish_diff(generated_manifest: dict, validation: dict, can_publish: bool) -> dict:
    if not can_publish:
        return {
            "status": "blocked",
            "changes": [],
            "blocked": validation.get("blocking", []),
            "change_count": 0,
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
    return {
        "status": "ready",
        "changes": changes,
        "blocked": [],
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


def _receipt(stage: str, severity: str, message: str, **extra) -> dict:
    return {
        "stage": stage,
        "severity": severity,
        "message": message,
        **{key: value for key, value in extra.items() if value is not None},
    }
