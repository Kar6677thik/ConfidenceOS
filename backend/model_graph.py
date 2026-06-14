"""
model_graph.py - Asset/signal graph helpers for generated HMI screens.

The graph is the source of truth for generated Runtime and Studio surfaces.
It is deliberately deterministic and file-backed for the demo.
"""

from __future__ import annotations

from asset_model import load_asset_model


def get_model_graph() -> dict:
    model = load_asset_model()
    assets = get_assets(model)
    signals = get_signals(model)
    nodes = []
    edges = []

    for asset in assets:
        nodes.append({
            "id": asset["asset_id"],
            "type": asset["asset_type"],
            "label": asset["name"],
            "template_id": asset.get("template_id"),
            "criticality": asset.get("criticality"),
            "parent_id": asset.get("parent_id"),
        })
    for signal in signals:
        nodes.append({
            "id": signal["tag"],
            "type": "signal",
            "label": signal.get("name", signal["tag"]),
            "sensor_type": signal.get("sensor_type"),
            "equipment_id": signal.get("equipment_id"),
            "criticality": signal.get("criticality"),
        })
        if signal.get("equipment_id"):
            edges.append({
                "source": signal["tag"],
                "target": signal["equipment_id"],
                "type": "measured_by",
            })

    for rel in model.get("graph_relationships", []):
        edges.append(dict(rel))

    return {
        "model_id": model.get("model_id"),
        "read_only_trust_layer": model.get("read_only_trust_layer", True),
        "integration_posture": model.get("integration_posture"),
        "nodes": nodes,
        "edges": edges,
        "navigation": get_navigation(model),
        "assets": assets,
        "signals": signals,
        "relationships": get_relationships(model),
    }


def get_navigation(model: dict | None = None) -> dict:
    model = model or load_asset_model()
    return model.get("hierarchy", {}).get("plant", {})


def get_assets(model: dict | None = None) -> list[dict]:
    model = model or load_asset_model()
    plant = model.get("hierarchy", {}).get("plant", {})
    assets = [{
        "asset_id": plant.get("id", "plant-a"),
        "name": plant.get("name", "Demo Plant"),
        "asset_type": "plant",
        "parent_id": None,
        "template_id": "plant_overview",
        "criticality": "high",
    }]
    for area in plant.get("areas", []):
        assets.append({
            "asset_id": area["id"],
            "name": area.get("name", area["id"]),
            "asset_type": "area",
            "parent_id": plant.get("id", "plant-a"),
            "template_id": "area_overview",
            "criticality": "medium",
        })
        for unit in area.get("units", []):
            assets.append({
                "asset_id": unit["id"],
                "name": unit.get("name", unit["id"]),
                "asset_type": "unit",
                "parent_id": area["id"],
                "template_id": "unit_overview",
                "criticality": "high",
            })
            for module in unit.get("modules", []):
                assets.append({
                    "asset_id": module["id"],
                    "name": module.get("name", module["id"]),
                    "asset_type": "module",
                    "parent_id": unit["id"],
                    "template_id": "module_overview",
                    "criticality": "high",
                    "equipment": module.get("equipment", []),
                })

    primary = model.get("equipment", {})
    if primary:
        assets.append(_equipment_asset(primary))
    for item in model.get("additional_equipment", []):
        assets.append(_equipment_asset(item))
    return assets


def get_signals(model: dict | None = None) -> list[dict]:
    model = model or load_asset_model()
    primary_equipment = model.get("equipment", {}).get("equipment_id", "V-5100")
    signals = []
    for tag in model.get("equipment", {}).get("sensor_tags", []):
        item = dict(tag)
        item["equipment_id"] = item.get("equipment_id") or primary_equipment
        item["id"] = item.get("tag")
        item["mapped"] = True
        signals.append(item)
    return signals


def get_relationships(model: dict | None = None) -> list[dict]:
    model = model or load_asset_model()
    relationships = list(model.get("equipment", {}).get("relationships", []))
    relationships.extend(model.get("graph_relationships", []))
    return relationships


def equipment_signals(equipment_id: str, model: dict | None = None) -> list[dict]:
    signals = get_signals(model)
    if equipment_id == model_or_primary_id(model):
        return [
            signal for signal in signals
            if signal.get("equipment_id") in (None, equipment_id, "V-5100")
            or signal.get("sensor_type") in ("level", "flow_in", "flow_out", "pressure", "temperature")
        ]
    return [signal for signal in signals if signal.get("equipment_id") == equipment_id]


def model_or_primary_id(model: dict | None = None) -> str:
    model = model or load_asset_model()
    return model.get("equipment", {}).get("equipment_id", "V-5100")


def _equipment_asset(item: dict) -> dict:
    return {
        "asset_id": item.get("equipment_id"),
        "name": item.get("name", item.get("equipment_id")),
        "asset_type": item.get("type", "equipment"),
        "parent_id": item.get("parent_module"),
        "template_id": item.get("template_id"),
        "criticality": item.get("criticality", "medium"),
        "signal_tags": item.get("signal_tags") or [tag.get("tag") for tag in item.get("sensor_tags", [])],
    }
