"""
assumptions.py - Engineering assumption register and deterministic confidence explanations.
"""

import json
from pathlib import Path


ASSUMPTIONS_PATH = Path(__file__).with_name("assumptions.json")

FACTOR_ASSUMPTIONS = {
    "calibration": ["confidence_weights", "calibration_interval"],
    "stability": ["confidence_weights", "stale_reading_threshold"],
    "cross_sensor": [
        "confidence_weights",
        "mass_balance_tolerance",
        "flow_to_level_conversion_factor",
    ],
    "physical_plausibility": ["confidence_weights", "operating_envelopes"],
    "none": ["confidence_weights"],
}

SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
STATUS_ORDER = {"BAD": 0, "DEGRADED": 1, "OK": 2, "INFO": 3}


def load_assumptions() -> dict:
    """Load the engineering assumption register from disk."""
    with ASSUMPTIONS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_confidence_explanation(
    sensor_id: str,
    confidence: dict,
    reading: dict | None,
    assumptions: dict | None = None,
) -> dict:
    """Build a deterministic, traceable explanation for one confidence result."""
    register = assumptions or load_assumptions()
    weights = register["confidence_weights"]["value"]
    sub_scores = confidence.get("sub_scores", {})
    dominant_factor = confidence.get("dominant_factor", "none")
    evidence = confidence.get("evidence", [])
    strongest = _strongest_evidence(evidence)
    counter = _counter_evidence(evidence)

    formula_terms = []
    for factor, weight in weights.items():
        score = sub_scores.get(factor)
        contribution = round(weight * score * 100, 1) if isinstance(score, (int, float)) else None
        formula_terms.append({
            "factor": factor,
            "weight": weight,
            "sub_score": score,
            "contribution_pct": contribution,
            "assumption_ids": FACTOR_ASSUMPTIONS.get(factor, ["confidence_weights"]),
        })

    return {
        "sensor_id": sensor_id,
        "sensor_type": (reading or {}).get("sensor_type"),
        "reading": reading,
        "confidence_pct": confidence.get("confidence_pct"),
        "tier": confidence.get("tier"),
        "formula": {
            "expression": (
                "confidence_pct = 100 * "
                "(0.30*calibration + 0.20*stability + "
                "0.30*cross_sensor + 0.20*physical_plausibility)"
            ),
            "terms": formula_terms,
            "computed_confidence_pct": confidence.get("confidence_pct"),
        },
        "sub_scores": sub_scores,
        "dominant_factor": dominant_factor,
        "strongest_evidence": strongest,
        "counter_evidence": counter,
        "verdict": _verdict(sensor_id, confidence, strongest, counter),
        "recommended_action": confidence.get("recommended_action"),
        "related_assumptions": _related_assumptions(dominant_factor, evidence, register),
    }


def _strongest_evidence(evidence: list[dict]) -> dict | None:
    if not evidence:
        return None
    non_ok = [item for item in evidence if item.get("status") != "OK"]
    candidates = non_ok or evidence
    return sorted(
        candidates,
        key=lambda item: (
            STATUS_ORDER.get(item.get("status"), 99),
            SEVERITY_ORDER.get(item.get("severity"), 99),
            item.get("category", ""),
        ),
    )[0]


def _counter_evidence(evidence: list[dict]) -> list[dict]:
    counter = [
        item for item in evidence
        if item.get("status") == "OK" or item.get("severity") == "INFO"
    ]
    return counter[:3]


def _verdict(sensor_id: str, confidence: dict, strongest: dict | None, counter: list[dict]) -> str:
    tier = confidence.get("tier", "HIGH")
    dominant = confidence.get("dominant_factor", "none")
    if tier == "HIGH":
        return f"{sensor_id} is acceptable as a primary reference under current assumptions."
    if tier == "MEDIUM":
        return f"{sensor_id} is degraded; use with cross-checks before treating it as a primary reference."
    if tier == "LOW":
        return f"Do not use {sensor_id} as the sole operating reference; dominant weakness is {dominant}."
    if strongest:
        return f"Do not trust {sensor_id} as a primary reference; strongest evidence is {strongest.get('category')}."
    if counter:
        return f"{sensor_id} remains critical despite available counter-evidence."
    return f"{sensor_id} is not acceptable as a primary operating reference."


def _related_assumptions(dominant_factor: str, evidence: list[dict], register: dict) -> list[dict]:
    assumption_ids = list(FACTOR_ASSUMPTIONS.get(dominant_factor, ["confidence_weights"]))
    for item in evidence:
        assumption_ids.extend(FACTOR_ASSUMPTIONS.get(item.get("category"), []))
    assumption_ids = list(dict.fromkeys(assumption_ids))
    return [
        {"assumption_id": assumption_id, **register[assumption_id]}
        for assumption_id in assumption_ids
        if assumption_id in register
    ]
