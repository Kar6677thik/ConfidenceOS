"""
asset_model.py - Lightweight demo vessel asset model helpers.

The asset model is intentionally small. It lets ConfidenceOS describe how it
observes tags, evidence, and affected decisions while remaining a read-only
trust layer beside the control system.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ASSET_MODEL_PATH = Path(__file__).with_name("asset_model.json")
ASSET_MODEL_PUMP_STATION_PATH = Path(__file__).with_name("asset_model_pump_station.json")

ASSET_MODELS = {
    "texas_city_vessel": {
        "label": "Texas City Demo Vessel",
        "path": ASSET_MODEL_PATH,
    },
    "pump_station": {
        "label": "Pump Station Demo",
        "path": ASSET_MODEL_PUMP_STATION_PATH,
    },
}
_active_asset_model_key = "texas_city_vessel"

CRITICALITY_WEIGHTS = {
    "low": 1.0,
    "medium": 1.5,
    "high": 2.0,
    "safety_critical": 3.0,
}


def available_asset_models() -> list[dict]:
    return [
        {"key": key, "label": meta["label"], "path": meta["path"].name}
        for key, meta in ASSET_MODELS.items()
    ]


def set_active_asset_model(model_key: str | None) -> str:
    global _active_asset_model_key
    if model_key in ASSET_MODELS:
        _active_asset_model_key = model_key
    return _active_asset_model_key


def active_asset_model_key() -> str:
    return _active_asset_model_key


@lru_cache(maxsize=4)
def _load_asset_model_by_key(model_key: str) -> dict:
    path = ASSET_MODELS.get(model_key, ASSET_MODELS["texas_city_vessel"])["path"]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_asset_model(model_key: str | None = None) -> dict:
    return _load_asset_model_by_key(model_key or _active_asset_model_key)


def equipment(model: dict | None = None) -> dict:
    return (model or load_asset_model()).get("equipment", {})


def sensor_tags(model: dict | None = None) -> list[dict]:
    return equipment(model).get("sensor_tags", [])


def sensor_by_tag(sensor_id: str, model: dict | None = None) -> dict:
    for tag in sensor_tags(model):
        if tag.get("tag") == sensor_id:
            return tag
    return {}


def sensor_ids_by_role(role: str, model: dict | None = None) -> list[str]:
    return [tag["tag"] for tag in sensor_tags(model) if tag.get("role") == role and tag.get("tag")]


def sensor_ids_by_type(sensor_type: str, model: dict | None = None) -> list[str]:
    return [tag["tag"] for tag in sensor_tags(model) if tag.get("sensor_type") == sensor_type and tag.get("tag")]


def mass_balance_validation(model: dict | None = None) -> dict:
    for rel in equipment(model).get("relationships", []):
        if rel.get("type") == "mass_balance_validation":
            return rel
    return {}


def affected_decisions(model: dict | None = None) -> list[dict]:
    return equipment(model).get("affected_decisions", [])


def action_contract_decisions(model: dict | None = None) -> list[str]:
    decisions = []
    for decision in affected_decisions(model):
        contract_decision = decision.get("contract_decision")
        if contract_decision:
            decisions.append(contract_decision)
    return list(dict.fromkeys(decisions))


def affected_decision_by_contract(contract_decision: str, model: dict | None = None) -> dict:
    for decision in affected_decisions(model):
        if decision.get("contract_decision") == contract_decision:
            return decision
    return {}


def trusted_substitute_tags(readings: list[dict], model: dict | None = None) -> list[str]:
    available = {reading.get("sensor_id") for reading in readings or []}
    rel = mass_balance_validation(model)
    substitutes = [tag for tag in rel.get("source_tags", []) if tag in available]
    for tag in sensor_tags(model):
        if tag.get("role") == "independent_process_reference" and tag.get("tag") in available:
            substitutes.append(tag["tag"])
    return list(dict.fromkeys(substitutes))


def criticality_weight(sensor_id: str, sensor_type: str | None = None, model: dict | None = None) -> float:
    tag = sensor_by_tag(sensor_id, model)
    if tag:
        return CRITICALITY_WEIGHTS.get(tag.get("criticality"), 1.0)
    fallback_by_type = {
        "level": 3.0,
        "flow_in": 2.0,
        "flow_out": 2.0,
        "pressure": 2.0,
        "temperature": 1.2,
        "valve": 1.5,
    }
    return fallback_by_type.get(sensor_type, 1.0)
