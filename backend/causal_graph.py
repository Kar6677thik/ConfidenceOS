"""
causal_graph.py — Causal Graph Explorer for ConfidenceOS V2 (Module 13).

Builds a directed graph of sensor relationships and highlights
probable causal chains when anomalies propagate across sensors.
"""

from datetime import datetime

from asset_model import load_asset_model, mass_balance_validation
from model_graph import get_signals


# Fallback sensor relationship graphs per plant topology, used only when the
# active asset model exposes no usable graph relationships. The live topology is
# now derived from the active model (see `_topology_from_model`), so the graph
# reflects whatever asset model is loaded rather than hardcoded Texas-City edges.
# Edges represent physical causal relationships:
#   A → B means "a problem with A can cause anomalous readings in B"

PLANT_TOPOLOGIES = {
    "plant-a": {
        "name": "Raffinate Splitter Unit",
        "edges": [
            ("ZT-6100", "FI-2010"),   # Valve → inflow
            ("ZT-6100", "FO-2020"),   # Valve → outflow
            ("FI-2010", "LT-5100"),   # Inflow → level
            ("FI-2010", "PT-3100"),   # Inflow → pressure
            ("FO-2020", "LT-5100"),   # Outflow → level
            ("LT-5100", "PT-3100"),   # Level → pressure
            ("PT-3100", "TT-4100"),   # Pressure → temperature
        ],
    },
    "plant-b": {
        "name": "North Sea Gas Compression",
        "edges": [
            ("ZT-6100", "FI-2010"),
            ("ZT-6100", "FO-2020"),
            ("FI-2010", "LT-5100"),
            ("FO-2020", "LT-5100"),
            ("PT-3100", "TT-4100"),
            ("TT-4100", "LT-5100"),   # Temperature → level (gas density)
            ("LT-5100", "PT-3100"),
        ],
    },
    "plant-c": {
        "name": "Municipal Water Treatment",
        "edges": [
            ("ZT-6100", "FI-2010"),
            ("ZT-6100", "FO-2020"),
            ("FI-2010", "LT-5100"),
            ("FO-2020", "LT-5100"),
            ("LT-5100", "PT-3100"),
            ("PT-3100", "TT-4100"),
        ],
    },
}


def _topology_from_model(plant_id: str) -> dict | None:
    """Derive a sensor→sensor causal topology from the active asset model.

    Sensor→sensor edges are obtained by (a) direct sensor-to-sensor graph
    relationships, (b) collapsing one non-sensor hop (e.g. FI → implied_level →
    LT becomes FI → LT, FI → V-5100 is dropped), and (c) the mass-balance
    relationship (each source tag → the validated tag). Returns None if the
    model yields no edges so the caller can fall back to the static topology.
    """
    try:
        model = load_asset_model()
    except Exception:
        return None

    signals = get_signals(model)
    sensor_ids = {s.get("tag") for s in signals if s.get("tag")}
    if not sensor_ids:
        return None

    raw = model.get("graph_relationships", [])
    adj: dict[str, list[str]] = {}
    for rel in raw:
        src, dst = rel.get("source"), rel.get("target")
        if src and dst:
            adj.setdefault(src, []).append(dst)

    edges: set[tuple[str, str]] = set()
    # (a) direct sensor → sensor relationships
    for rel in raw:
        src, dst = rel.get("source"), rel.get("target")
        if src in sensor_ids and dst in sensor_ids and src != dst:
            edges.add((src, dst))
    # (b) collapse a single non-sensor intermediate node (equipment / implied_level)
    for src, targets in adj.items():
        if src not in sensor_ids:
            continue
        for mid in targets:
            if mid in sensor_ids:
                continue
            for dst in adj.get(mid, []):
                if dst in sensor_ids and dst != src:
                    edges.add((src, dst))
    # (c) mass-balance: each source tag drives the validated tag
    rel = mass_balance_validation(model)
    validated = rel.get("validated_tag")
    if validated in sensor_ids:
        for src in rel.get("source_tags", []):
            if src in sensor_ids and src != validated:
                edges.add((src, validated))

    if not edges:
        return None

    plant = model.get("hierarchy", {}).get("plant", {})
    name = plant.get("name") or model.get("model_id") or "Active Asset Model"
    return {
        "name": name,
        "edges": sorted(edges),
        "sensor_ids": sorted(sensor_ids),
        "source": "active_asset_model",
    }


def get_graph_state(plant_id: str, confidence_data: dict) -> dict:
    """
    Get the current causal graph state with nodes colored by confidence tier
    and edges highlighted when both endpoints are anomalous.

    Args:
        plant_id: which plant
        confidence_data: {sensor_id: {confidence_pct, tier, reasons, ...}}

    Returns:
        dict with 'nodes', 'edges', 'causal_chains', 'root_cause', 'narrative'
    """
    # Prefer the live, metadata-driven topology; fall back to static demo edges.
    topology = _topology_from_model(plant_id) or PLANT_TOPOLOGIES.get(plant_id, PLANT_TOPOLOGIES["plant-a"])

    # Build the node set from the model's full signal list when available, so
    # every sensor appears even if it has no causal edge; otherwise from edges.
    all_sensor_ids = set(topology.get("sensor_ids", []))
    for src, dst in topology["edges"]:
        all_sensor_ids.add(src)
        all_sensor_ids.add(dst)

    nodes = []
    for sid in sorted(all_sensor_ids):
        conf = confidence_data.get(sid, {})
        tier = conf.get("tier", "HIGH")
        pct = conf.get("confidence_pct", 100)
        reasons = conf.get("reasons", [])
        
        nodes.append({
            "id": sid,
            "confidence_pct": pct,
            "tier": tier,
            "reasons": reasons[:2],
            "is_anomalous": tier in ("LOW", "CRITICAL"),
            "is_degraded": tier in ("LOW", "CRITICAL", "MEDIUM"),
        })

    # Build edges
    edges = []
    for src, dst in topology["edges"]:
        src_conf = confidence_data.get(src, {})
        dst_conf = confidence_data.get(dst, {})
        src_anom = src_conf.get("tier", "HIGH") in ("LOW", "CRITICAL")
        dst_anom = dst_conf.get("tier", "HIGH") in ("LOW", "CRITICAL")
        
        edges.append({
            "source": src,
            "target": dst,
            "is_active": src_anom and dst_anom,  # Both endpoints anomalous
            "is_propagating": src_anom or dst_anom,  # At least one anomalous
        })

    # Find causal chains
    anomalous_sensors = {
        sid for sid, conf in confidence_data.items()
        if conf.get("tier") in ("LOW", "CRITICAL")
    }
    
    causal_chains = []
    root_cause = None

    if anomalous_sensors:
        # Build adjacency map for traversal
        adj = {}
        predecessors = {}
        for src, dst in topology["edges"]:
            adj.setdefault(src, []).append(dst)
            predecessors.setdefault(dst, []).append(src)

        # Find root cause: anomalous sensor with no anomalous predecessors
        candidates = []
        for sid in anomalous_sensors:
            preds = predecessors.get(sid, [])
            has_anom_pred = any(p in anomalous_sensors for p in preds)
            if not has_anom_pred:
                candidates.append(sid)

        if candidates:
            # Pick the one with lowest confidence as root
            root_cause = min(
                candidates,
                key=lambda s: confidence_data.get(s, {}).get("confidence_pct", 100)
            )

            # Trace causal chain from root
            chain = _trace_chain(root_cause, adj, anomalous_sensors)
            if len(chain) > 1:
                causal_chains.append(chain)

    # Generate narrative
    narrative = _generate_narrative(root_cause, causal_chains, confidence_data)

    return {
        "plant_id": plant_id,
        "plant_name": topology["name"],
        "nodes": nodes,
        "edges": edges,
        "causal_chains": causal_chains,
        "root_cause": root_cause,
        "narrative": narrative,
    }


def _trace_chain(start: str, adj: dict, anomalous: set, visited: set = None) -> list:
    """BFS trace from root cause through anomalous sensors."""
    if visited is None:
        visited = set()
    
    chain = [start]
    visited.add(start)
    
    for neighbor in adj.get(start, []):
        if neighbor in anomalous and neighbor not in visited:
            chain.extend(_trace_chain(neighbor, adj, anomalous, visited))
    
    return chain


def _generate_narrative(root_cause, causal_chains, confidence_data):
    """Generate a plain-English explanation of the causal chain."""
    if not root_cause:
        return "No active anomaly chains detected. All sensor relationships are within normal operating parameters."

    root_conf = confidence_data.get(root_cause, {})
    root_pct = root_conf.get("confidence_pct", 0)
    root_reasons = root_conf.get("reasons", [])

    narrative = f"Root cause analysis: {root_cause} is the probable origin of the current anomaly chain "
    narrative += f"(confidence: {root_pct:.0f}%). "

    if root_reasons:
        narrative += f"Primary issue: {root_reasons[0]}. "

    if causal_chains:
        chain = causal_chains[0]
        if len(chain) > 1:
            path = " → ".join(chain)
            narrative += f"Propagation path: {path}. "
            narrative += f"Resolving {root_cause} may improve readings for downstream sensors."

    return narrative
