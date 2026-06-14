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

CRITICALITY_WEIGHTS = {
    "low": 1.0,
    "medium": 1.5,
    "high": 2.0,
    "safety_critical": 3.0,
}


@lru_cache(maxsize=1)
def load_asset_model() -> dict:
    with open(ASSET_MODEL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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
