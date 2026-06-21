"""
assumptions.py - Engineering assumption register and deterministic confidence explanations.
"""

import json
from datetime import date, datetime, timezone
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
GOVERNANCE_FIELDS = {
    "version",
    "effective_date",
    "last_reviewed_at",
    "next_review_due",
    "approval_status",
    "approved_by",
    "approval_role",
    "moc_reference",
}
APPROVAL_STATUSES = {"approved", "review_required", "draft", "rejected"}
DUE_SOON_DAYS = 30


def load_assumptions() -> dict:
    """Load the engineering assumption register from disk."""
    with ASSUMPTIONS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_assumption_governance(register: dict | None = None, now: date | datetime | str | None = None) -> dict:
    """Return deterministic governance status for the engineering assumption register."""
    assumptions = register or load_assumptions()
    today = _coerce_date(now) or date.today()
    warnings = []
    by_status = {"approved": 0, "due_soon": 0, "stale": 0, "unapproved": 0}
    stale_ids = []
    unapproved_ids = []
    due_soon_ids = []
    high_impact_open_items = []
    items = []

    for assumption_id, assumption in assumptions.items():
        governance = _assumption_governance_status(assumption_id, assumption, today)
        status = governance["governance_status"]
        by_status[status] = by_status.get(status, 0) + 1
        items.append({"assumption_id": assumption_id, **governance})

        if status == "stale":
            stale_ids.append(assumption_id)
        if status == "unapproved":
            unapproved_ids.append(assumption_id)
        if status == "due_soon":
            due_soon_ids.append(assumption_id)
        if governance.get("review_warning"):
            warnings.append(governance["review_warning"])
        if assumption.get("confidence_impact") == "high" and status in {"stale", "unapproved", "due_soon"}:
            high_impact_open_items.append({
                "assumption_id": assumption_id,
                "governance_status": status,
                "confidence_impact": assumption.get("confidence_impact"),
                "owner_role": assumption.get("owner_role"),
                "next_review_due": assumption.get("next_review_due"),
                "moc_reference": assumption.get("moc_reference"),
                "review_warning": governance.get("review_warning"),
            })

    if unapproved_ids or stale_ids:
        status = "WARNING"
    elif due_soon_ids:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "status": status,
        "summary": {
            "total": len(assumptions),
            "approved": by_status.get("approved", 0),
            "due_soon": by_status.get("due_soon", 0),
            "stale": by_status.get("stale", 0),
            "unapproved": by_status.get("unapproved", 0),
            "review_required": sum(1 for item in assumptions.values() if item.get("review_required")),
        },
        "warnings": warnings,
        "stale_assumption_ids": stale_ids,
        "unapproved_assumption_ids": unapproved_ids,
        "due_soon_assumption_ids": due_soon_ids,
        "high_impact_open_items": high_impact_open_items,
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "stale_if_past_next_review_due": True,
            "unapproved_warns": True,
            "due_soon_days": DUE_SOON_DAYS,
            "confidence_score_type": "governed trust rubric, not calibrated probability",
        },
    }


def decorate_related_assumptions_with_governance(assumptions: list[dict], now: date | datetime | str | None = None) -> list[dict]:
    """Attach derived governance fields to assumption rows used by evidence ledgers."""
    today = _coerce_date(now) or date.today()
    decorated = []
    for item in assumptions:
        assumption_id = item.get("assumption_id", "unknown_assumption")
        decorated.append({
            **item,
            **_assumption_governance_status(assumption_id, item, today),
        })
    return decorated


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
            "expression": _formula_expression(weights),
            "terms": formula_terms,
            "computed_confidence_pct": confidence.get("confidence_pct"),
        },
        "sub_scores": sub_scores,
        "dominant_factor": dominant_factor,
        "strongest_evidence": strongest,
        "counter_evidence": counter,
        "verdict": _verdict(sensor_id, confidence, strongest, counter),
        "recommended_action": confidence.get("recommended_action"),
        "related_assumptions": decorate_related_assumptions_with_governance(
            _related_assumptions(dominant_factor, evidence, register)
        ),
    }


def confidence_formula_expression(assumptions: dict | None = None) -> str:
    """Return the governed confidence expression used in explanations and receipts."""
    register = assumptions or load_assumptions()
    return _formula_expression(register["confidence_weights"]["value"])


def confidence_engine_config(assumptions: dict | None = None) -> dict:
    """Return ConfidenceEngine constructor/config values from the governed register."""
    from confidence import ConfidenceWeights

    register = assumptions or load_assumptions()
    weights = register["confidence_weights"]["value"]
    return {
        "weights": ConfidenceWeights(
            calibration=float(weights.get("calibration", 0.30)),
            stability=float(weights.get("stability", 0.20)),
            cross_sensor=float(weights.get("cross_sensor", 0.30)),
            physical_plausibility=float(weights.get("physical_plausibility", 0.20)),
        ),
        "calibration_interval_days": float(register["calibration_interval"]["value"]),
        "per_sensor_type_calibration_intervals": register.get(
            "per_sensor_type_calibration_intervals", {}
        ).get("value", {}),
        "per_sensor_type_confidence_weights": {
            sensor_type: ConfidenceWeights(
                calibration=float(w.get("calibration", 0.30)),
                stability=float(w.get("stability", 0.20)),
                cross_sensor=float(w.get("cross_sensor", 0.30)),
                physical_plausibility=float(w.get("physical_plausibility", 0.20)),
            )
            for sensor_type, w in register.get(
                "per_sensor_type_confidence_weights", {}
            ).get("value", {}).items()
        },
        "operating_envelopes": register["operating_envelopes"]["value"],
        "assumption_ids": [
            "confidence_weights",
            "calibration_interval",
            "per_sensor_type_calibration_intervals",
            "per_sensor_type_confidence_weights",
            "operating_envelopes",
        ],
    }


def startup_config(assumptions: dict | None = None) -> dict:
    """Return StartupManager config values from the governed register."""
    register = assumptions or load_assumptions()
    thresholds = register["startup_thresholds"]["value"]
    return {
        "normal_tiers": thresholds.get("normal", {}),
        "startup_tiers": thresholds.get("startup", {}),
        "mass_balance_tolerance_multiplier": float(thresholds.get("mass_balance_tolerance_multiplier", 0.5)),
        "stale_threshold_seconds": float(register["stale_reading_threshold"]["value"]),
    }


def _formula_expression(weights: dict) -> str:
    ordered = ["calibration", "stability", "cross_sensor", "physical_plausibility"]
    terms = [f"{weights.get(factor, 0):.2f}*{factor}" for factor in ordered]
    return f"confidence_pct = 100 * ({' + '.join(terms)})"


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


def _coerce_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def _assumption_governance_status(assumption_id: str, assumption: dict, today: date) -> dict:
    missing = sorted(field for field in GOVERNANCE_FIELDS if not assumption.get(field))
    approval_status = str(assumption.get("approval_status") or "").lower()
    if approval_status and approval_status not in APPROVAL_STATUSES:
        missing.append("valid_approval_status")

    next_review_due = _coerce_date(assumption.get("next_review_due"))
    last_reviewed = _coerce_date(assumption.get("last_reviewed_at"))
    review_required = bool(assumption.get("review_required"))

    if missing or approval_status != "approved":
        status = "unapproved"
        reason = "missing governance metadata" if missing else f"approval status is {approval_status or 'missing'}"
    elif review_required and next_review_due and next_review_due < today:
        status = "stale"
        reason = f"review was due on {next_review_due.isoformat()}"
    elif review_required and next_review_due and (next_review_due - today).days <= DUE_SOON_DAYS:
        status = "due_soon"
        reason = f"review due on {next_review_due.isoformat()}"
    else:
        status = "approved"
        reason = "approved governance metadata is current"

    warning = None
    if status == "unapproved":
        warning = f"{assumption_id} is unapproved: {reason}."
    elif status == "stale":
        warning = f"{assumption_id} is a stale assumption: {reason}."
    elif status == "due_soon":
        warning = f"{assumption_id} review required soon: {reason}."

    return {
        "governance_status": status,
        "review_warning": warning,
        "missing_governance_fields": missing,
        "review_required": review_required,
        "last_reviewed_at": last_reviewed.isoformat() if last_reviewed else assumption.get("last_reviewed_at"),
        "next_review_due": next_review_due.isoformat() if next_review_due else assumption.get("next_review_due"),
        "approval_status": assumption.get("approval_status"),
        "approved_by": assumption.get("approved_by"),
        "approval_role": assumption.get("approval_role"),
        "moc_reference": assumption.get("moc_reference"),
        "version": assumption.get("version"),
        "confidence_impact": assumption.get("confidence_impact"),
        "owner_role": assumption.get("owner_role"),
    }
