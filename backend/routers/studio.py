"""
routers/studio.py — Studio, model, template and screen-generation routes.

All /api/studio/*, /api/model/*, /api/templates, /api/screens/generated,
/api/runtime/navigation|situations|equipment endpoints live here.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import deps
from auth import require_role
from model_graph import get_assets, get_model_graph, get_navigation, get_signals
from screen_generator import equipment_manifest, generate_screen_manifest
from template_library import get_template_catalog
from studio_service import (
    assign_template as studio_assign_template,
    auto_map as studio_auto_map,
    approve_raw_tag as studio_approve_raw_tag,
    current_build as studio_current_build,
    diff as studio_diff,
    generate_preview as studio_generate_preview,
    ignore_raw_tag as studio_ignore_raw_tag,
    import_arbitrary_tags as studio_import_arbitrary_tags,
    imported_signals as studio_imported_signals,
    keep_raw_tag_blocking as studio_keep_raw_tag_blocking,
    mapping_court_detail as studio_mapping_court_detail,
    mapping_court_items as studio_mapping_court,
    manual_map_raw_tag as studio_manual_map_raw_tag,
    persisted_build_artifacts as studio_persisted_build_artifacts,
    persisted_import_batches as studio_persisted_import_batches,
    publish as studio_publish,
    reset as studio_reset,
    runtime_manifest as studio_runtime_manifest,
    run_compiler_build as studio_run_compiler_build,
    select_asset_model as studio_select_asset_model,
    studio_overview,
    suggest_template_for_asset as studio_suggest_template,
    template_tests as studio_template_tests,
    update_template_mutation as studio_update_template_mutation,
    validation as studio_validation,
)

router = APIRouter()

plant_manager = deps.plant_manager
_plant_loop_status = deps.plant_loop_status


def _fallback_runtime_live_state(plant_id: str, plant) -> dict:
    """Minimal live-state fallback if main.py has not registered helpers yet."""
    return {
        "plant_id": plant_id,
        "readings": getattr(plant, "latest_readings", []),
        "confidence": list(getattr(plant, "latest_confidence", {}).values()),
        "mass_balance": getattr(plant, "latest_mb_state", {}),
        "mode": getattr(plant, "latest_mode_payload", {}),
        "plant_context": getattr(plant, "latest_context", {}),
        "incidents": getattr(plant, "latest_incidents", []),
        "incident_timeline": getattr(plant, "latest_incident_timeline", []),
        "verification_tokens": getattr(plant, "verification_tokens", []),
        "verification_tasks": getattr(plant, "verification_tokens", []),
        "handover_debt": getattr(plant, "latest_handover_debt", {}),
        "confidence_debt": getattr(plant, "latest_confidence_debt", []),
        "live_binding_status": "native_live_tags" if getattr(plant, "latest_readings", []) else "metadata_only_no_live_tags",
        "demo_alias_bindings": [],
        "unbound_tags": [],
    }


def _annotate_generated_preview(manifest: dict, live_state: dict) -> dict:
    annotate = getattr(deps, "annotate_generated_preview", None)
    if callable(annotate):
        return annotate(manifest, live_state)
    publish_state = str(manifest.get("runtime_publish_state") or manifest.get("validation_status") or "").upper()
    authority = manifest.get("runtime_authority") or ("published" if publish_state.startswith("PUBLISHED") else "preview")
    preview = authority != "published" or publish_state in {"NOT_PUBLISHED", "FAILED", "BLOCKED"}
    return {
        **manifest,
        "runtime_authority": authority,
        "operator_authoritative": authority == "published",
        "plant_id": live_state.get("plant_id", "plant-a"),
        "runtime_preview": preview,
        "live_binding_status": live_state.get("live_binding_status", "metadata_only_no_live_tags"),
        "demo_alias_bindings": live_state.get("demo_alias_bindings", []),
        "unbound_tags": live_state.get("unbound_tags", []),
        "demo_state": live_state.get("demo_state"),
        "read_only_trust_layer": True,
    }


def _runtime_live_state(plant_id: str, plant, model_key: str | None = None) -> dict:
    live_state = getattr(deps, "runtime_live_state", None)
    if callable(live_state):
        try:
            return live_state(plant_id, plant, model_key=model_key)
        except TypeError:
            return live_state(plant_id, plant)
    return _fallback_runtime_live_state(plant_id, plant)


# ── Pydantic models ───────────────────────────────────────────────────────────

class StudioTemplateAssignmentRequest(BaseModel):
    asset_id: str
    template_id: str
    approved: bool = True


class StudioGenerateRequest(BaseModel):
    role: str = "Engineer"
    context: str = "auto"


class StudioRawTagResolutionRequest(BaseModel):
    raw_tag: str
    reason: str = ""


class StudioManualMapRequest(BaseModel):
    raw_tag: str
    canonical_tag: str
    asset_id: str
    signal_role: str
    reason: str


class StudioAssetModelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_key: str


class StudioTemplateMutationRequest(BaseModel):
    require_manual_verification_when_level_quarantined: bool = False


# ── Model / asset graph routes ────────────────────────────────────────────────

@router.get("/api/model/graph")
def get_model_graph_endpoint(model_key: Optional[str] = Query(default=None)):
    return get_model_graph(model_key=model_key)


@router.get("/api/model/assets")
def get_model_assets(model_key: Optional[str] = Query(default=None)):
    assets = get_assets(model_key=model_key)
    return {"assets": assets, "count": len(assets)}


@router.get("/api/model/signals")
def get_model_signals(model_key: Optional[str] = Query(default=None)):
    signals = get_signals(model_key=model_key)
    return {"signals": signals, "count": len(signals), "source": "asset_model.json"}


@router.get("/api/templates")
def get_templates():
    return get_template_catalog()


# ── Screen generation ─────────────────────────────────────────────────────────

@router.get("/api/screens/generated")
def get_generated_screens(
    role: str = Query(default="Operator"),
    context: str = Query(default="auto"),
    plant_id: str = Query(default="plant-a"),
    model_key: Optional[str] = Query(default=None),
):
    plant = plant_manager.get(plant_id)
    effective_model_key = model_key or getattr(plant, "model_key", None)
    live_state = _runtime_live_state(plant_id, plant, model_key=effective_model_key)
    try:
        manifest = studio_runtime_manifest(role=role, context=context, live_state=live_state, model_key=effective_model_key)
        if manifest.get("runtime_authority") != "published" and role not in {"Engineer", "Manager"}:
            raise HTTPException(status_code=409, detail={
                "runtime_authority": manifest.get("runtime_authority", "preview"),
                "operator_authoritative": False,
                "model_key": manifest.get("model_key") or effective_model_key,
                "reason": manifest.get("runtime_notice") or "No published Runtime exists for this asset model.",
                "read_only_trust_layer": True,
            })
        return _annotate_generated_preview(manifest, live_state)
    except HTTPException:
        raise
    except Exception as exc:
        if role not in {"Engineer", "Manager"}:
            raise HTTPException(status_code=503, detail={
                "runtime_authority": "unavailable",
                "operator_authoritative": False,
                "model_key": effective_model_key,
                "reason": "Published Runtime manifest could not be hydrated.",
                "error": str(exc),
                "read_only_trust_layer": True,
            })
        assignments = studio_overview(effective_model_key).get("state", {}).get("assignments", [])
        manifest = generate_screen_manifest(
            role=role, context=context, live_state=live_state, assignments=assignments,
            build_context={
                "build_id": "runtime-fallback",
                "validation_status": "PASS_WITH_WARNINGS",
                "model_key": effective_model_key,
                "validation": {
                    "info": [{"rule": "runtime_fallback_generation",
                              "message": "Generated fallback Runtime because published manifest hydration failed."}],
                    "warnings": [{"rule": "runtime_manifest_hydration_failed", "message": str(exc)}],
                    "blocking": [],
                },
                "receipts": [{"severity": "WARNING",
                               "message": "Runtime fallback generated from asset model and template assignments.",
                               "source": "api/screens/generated"}],
            },
            model_key=effective_model_key,
        )
        return _annotate_generated_preview({**manifest, "runtime_source": "fallback_runtime_generation",
                                            "runtime_authority": "fallback",
                                            "operator_authoritative": False,
                                            "runtime_warning": str(exc)}, live_state)


# ── Runtime navigation / situations ──────────────────────────────────────────

@router.get("/api/runtime/navigation")
def get_runtime_navigation(model_key: Optional[str] = Query(default=None)):
    return {
        "navigation": get_navigation(model_key=model_key),
        "semantic_zoom": ["plant", "area", "unit", "module", "equipment", "signal"],
    }


@router.get("/api/runtime/situations")
def get_runtime_situations(plant_id: str = Query(default="plant-a")):
    plant = plant_manager.get(plant_id)
    return {
        "plant_id": plant_id,
        "situations": plant.latest_incidents,
        "count": len(plant.latest_incidents),
        "context": plant.latest_context,
    }


@router.get("/api/runtime/equipment/{equipment_id}")
def get_runtime_equipment(
    equipment_id: str,
    role: str = Query(default="Operator"),
    plant_id: str = Query(default="plant-a"),
    model_key: Optional[str] = Query(default=None),
):
    plant = plant_manager.get(plant_id)
    effective_model_key = model_key or getattr(plant, "model_key", None)
    faceplate = equipment_manifest(
        equipment_id, role,
        live_state=_runtime_live_state(plant_id, plant, model_key=effective_model_key),
        assignments=studio_overview(effective_model_key)["state"].get("assignments", []),
        model_key=effective_model_key,
    )
    if not faceplate:
        raise HTTPException(status_code=404, detail=f"Equipment not found: {equipment_id}")
    return faceplate


# ── Studio routes ─────────────────────────────────────────────────────────────

@router.get("/api/studio/imported-signals")
def get_studio_imported_signals(model_key: Optional[str] = Query(default=None)):
    return studio_imported_signals(model_key=model_key)


@router.post("/api/studio/asset-model", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_asset_model(request: StudioAssetModelRequest):
    return studio_select_asset_model(request.model_key)


@router.post("/api/studio/template-mutation", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_template_mutation(
    request: StudioTemplateMutationRequest,
    model_key: Optional[str] = Query(default=None),
):
    return studio_update_template_mutation(
        request.require_manual_verification_when_level_quarantined,
        model_key=model_key,
    )


@router.get("/api/studio/build")
def get_studio_build(model_key: Optional[str] = Query(default=None)):
    return studio_current_build(model_key=model_key)


@router.post("/api/studio/build/run", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_build_run(model_key: Optional[str] = Query(default=None)):
    return studio_run_compiler_build(model_key=model_key)


@router.get("/api/studio/build/artifacts")
def get_studio_build_artifacts(
    model_key: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    return studio_persisted_build_artifacts(model_key=model_key, limit=limit)


@router.get("/api/studio/import-batches")
def get_studio_import_batches(
    model_key: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    return studio_persisted_import_batches(model_key=model_key, limit=limit)


@router.get("/api/studio/template-tests")
def get_studio_template_tests(model_key: Optional[str] = Query(default=None)):
    return studio_template_tests(model_key=model_key)


@router.get("/api/studio/mapping-court")
def get_studio_mapping_court(model_key: Optional[str] = Query(default=None)):
    return studio_mapping_court(model_key=model_key)


@router.get("/api/studio/mapping-court/{raw_tag:path}")
def get_studio_mapping_court_detail(raw_tag: str, model_key: Optional[str] = Query(default=None)):
    return studio_mapping_court_detail(raw_tag, model_key=model_key)


@router.post("/api/studio/mapping-court/approve", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_mapping_approve(request: StudioRawTagResolutionRequest, model_key: Optional[str] = Query(default=None)):
    result = studio_approve_raw_tag(request.raw_tag, model_key=model_key)
    if result.get("status") == "not_approved":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/api/studio/mapping-court/ignore", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_mapping_ignore(request: StudioRawTagResolutionRequest, model_key: Optional[str] = Query(default=None)):
    result = studio_ignore_raw_tag(request.raw_tag, request.reason, model_key=model_key)
    if result.get("status") == "not_ignored":
        raise HTTPException(status_code=422, detail=result)
    return result


@router.post("/api/studio/mapping-court/manual-map", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_mapping_manual_map(request: StudioManualMapRequest, model_key: Optional[str] = Query(default=None)):
    result = studio_manual_map_raw_tag(
        request.raw_tag, request.canonical_tag,
        request.asset_id, request.signal_role, request.reason,
        model_key=model_key,
    )
    if result.get("status") == "not_mapped":
        raise HTTPException(status_code=422, detail=result)
    return result


@router.post("/api/studio/mapping-court/keep-blocking", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_mapping_keep_blocking(request: StudioRawTagResolutionRequest, model_key: Optional[str] = Query(default=None)):
    return studio_keep_raw_tag_blocking(request.raw_tag, model_key=model_key)


@router.post("/api/studio/auto-map", dependencies=[Depends(require_role("Engineer", "Manager"))])
async def post_studio_auto_map(model_key: Optional[str] = Query(default=None)):
    return await studio_auto_map(model_key=model_key)


@router.post("/api/studio/import-tags", dependencies=[Depends(require_role("Engineer", "Manager"))])
async def post_studio_import_tags(request: dict, model_key: Optional[str] = Query(default=None)):
    raw_tags = request.get("tags", [])
    if not isinstance(raw_tags, list):
        raise HTTPException(status_code=422, detail="'tags' must be a list of strings.")
    cleaned = [str(t).strip() for t in raw_tags if str(t).strip()]
    if not cleaned:
        raise HTTPException(status_code=422, detail="No non-empty tags provided.")
    return await studio_import_arbitrary_tags(cleaned, model_key=model_key)


@router.post("/api/studio/suggest-template", dependencies=[Depends(require_role("Engineer", "Manager"))])
async def post_studio_suggest_template(request: dict, model_key: Optional[str] = Query(default=None)):
    description = (request.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="'description' is required.")
    return await studio_suggest_template(description, model_key=model_key)


@router.post("/api/studio/assign-template", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_assign_template(request: StudioTemplateAssignmentRequest, model_key: Optional[str] = Query(default=None)):
    return studio_assign_template(request.asset_id, request.template_id, approved=request.approved, model_key=model_key)


@router.post("/api/studio/generate", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_generate(request: StudioGenerateRequest | None = None, model_key: Optional[str] = Query(default=None)):
    payload = request or StudioGenerateRequest()
    return studio_generate_preview(role=payload.role, context=payload.context, model_key=model_key)


@router.post("/api/studio/publish", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_publish(model_key: Optional[str] = Query(default=None)):
    result = studio_publish(model_key=model_key)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/api/studio/reset", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_reset(model_key: Optional[str] = Query(default=None)):
    return studio_reset(model_key=model_key)


@router.get("/api/studio/validation")
def get_studio_validation(model_key: Optional[str] = Query(default=None)):
    return studio_validation(model_key=model_key)


@router.get("/api/studio/diff")
def get_studio_diff(model_key: Optional[str] = Query(default=None)):
    return studio_diff(model_key=model_key)


@router.get("/api/studio")
def get_studio_overview(model_key: Optional[str] = Query(default=None)):
    return studio_overview(model_key)
