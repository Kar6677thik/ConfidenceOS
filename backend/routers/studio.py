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
from asset_model import active_asset_model_key
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
def get_model_graph_endpoint():
    return get_model_graph()


@router.get("/api/model/assets")
def get_model_assets():
    assets = get_assets()
    return {"assets": assets, "count": len(assets)}


@router.get("/api/model/signals")
def get_model_signals():
    signals = get_signals()
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
):
    # Lazy import avoids circular import; main is fully loaded by request time.
    import main as _main
    plant = plant_manager.get(plant_id)
    live_state = _main._runtime_live_state(plant_id, plant)
    try:
        manifest = studio_runtime_manifest(role=role, context=context, live_state=live_state)
        return _main._annotate_generated_preview(manifest, live_state)
    except Exception as exc:
        assignments = studio_overview().get("state", {}).get("assignments", [])
        manifest = generate_screen_manifest(
            role=role, context=context, live_state=live_state, assignments=assignments,
            build_context={
                "build_id": "runtime-fallback",
                "validation_status": "PASS_WITH_WARNINGS",
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
        )
        return _main._annotate_generated_preview({**manifest, "runtime_source": "fallback_runtime_generation",
                                                   "runtime_warning": str(exc)}, live_state)


# ── Runtime navigation / situations ──────────────────────────────────────────

@router.get("/api/runtime/navigation")
def get_runtime_navigation():
    return {
        "navigation": get_navigation(),
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
):
    import main as _main
    plant = plant_manager.get(plant_id)
    faceplate = equipment_manifest(
        equipment_id, role,
        live_state=_main._runtime_live_state(plant_id, plant),
        assignments=studio_overview()["state"].get("assignments", []),
    )
    if not faceplate:
        raise HTTPException(status_code=404, detail=f"Equipment not found: {equipment_id}")
    return faceplate


# ── Studio routes ─────────────────────────────────────────────────────────────

@router.get("/api/studio/imported-signals")
def get_studio_imported_signals():
    return studio_imported_signals()


@router.post("/api/studio/asset-model", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_asset_model(request: StudioAssetModelRequest):
    return studio_select_asset_model(request.model_key)


@router.post("/api/studio/template-mutation")
def post_studio_template_mutation(request: StudioTemplateMutationRequest):
    return studio_update_template_mutation(request.require_manual_verification_when_level_quarantined)


@router.get("/api/studio/build")
def get_studio_build():
    return studio_current_build()


@router.post("/api/studio/build/run")
def post_studio_build_run():
    return studio_run_compiler_build()


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
def get_studio_template_tests():
    return studio_template_tests()


@router.get("/api/studio/mapping-court")
def get_studio_mapping_court():
    return studio_mapping_court()


@router.get("/api/studio/mapping-court/{raw_tag:path}")
def get_studio_mapping_court_detail(raw_tag: str):
    return studio_mapping_court_detail(raw_tag)


@router.post("/api/studio/mapping-court/approve")
def post_studio_mapping_approve(request: StudioRawTagResolutionRequest):
    result = studio_approve_raw_tag(request.raw_tag)
    if result.get("status") == "not_approved":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/api/studio/mapping-court/ignore")
def post_studio_mapping_ignore(request: StudioRawTagResolutionRequest):
    result = studio_ignore_raw_tag(request.raw_tag, request.reason)
    if result.get("status") == "not_ignored":
        raise HTTPException(status_code=422, detail=result)
    return result


@router.post("/api/studio/mapping-court/manual-map")
def post_studio_mapping_manual_map(request: StudioManualMapRequest):
    result = studio_manual_map_raw_tag(
        request.raw_tag, request.canonical_tag,
        request.asset_id, request.signal_role, request.reason,
    )
    if result.get("status") == "not_mapped":
        raise HTTPException(status_code=422, detail=result)
    return result


@router.post("/api/studio/mapping-court/keep-blocking")
def post_studio_mapping_keep_blocking(request: StudioRawTagResolutionRequest):
    return studio_keep_raw_tag_blocking(request.raw_tag)


@router.post("/api/studio/auto-map")
async def post_studio_auto_map():
    return await studio_auto_map()


@router.post("/api/studio/import-tags")
async def post_studio_import_tags(request: dict):
    raw_tags = request.get("tags", [])
    if not isinstance(raw_tags, list):
        raise HTTPException(status_code=422, detail="'tags' must be a list of strings.")
    cleaned = [str(t).strip() for t in raw_tags if str(t).strip()]
    if not cleaned:
        raise HTTPException(status_code=422, detail="No non-empty tags provided.")
    return await studio_import_arbitrary_tags(cleaned)


@router.post("/api/studio/suggest-template")
async def post_studio_suggest_template(request: dict):
    description = (request.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="'description' is required.")
    return await studio_suggest_template(description)


@router.post("/api/studio/assign-template")
def post_studio_assign_template(request: StudioTemplateAssignmentRequest):
    return studio_assign_template(request.asset_id, request.template_id, approved=request.approved)


@router.post("/api/studio/generate")
def post_studio_generate(request: StudioGenerateRequest | None = None):
    payload = request or StudioGenerateRequest()
    return studio_generate_preview(role=payload.role, context=payload.context)


@router.post("/api/studio/publish", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_publish():
    result = studio_publish()
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/api/studio/reset", dependencies=[Depends(require_role("Engineer", "Manager"))])
def post_studio_reset():
    return studio_reset()


@router.get("/api/studio/validation")
def get_studio_validation():
    return studio_validation()


@router.get("/api/studio/diff")
def get_studio_diff():
    return studio_diff()


@router.get("/api/studio")
def get_studio_overview():
    return studio_overview()
