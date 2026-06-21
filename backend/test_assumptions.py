"""
test_assumptions.py - Tests for engineering assumptions and confidence explanations.

Run from backend directory:
    python test_assumptions.py
"""

import sys

from datetime import date

from assumptions import (
    build_assumption_governance,
    build_confidence_explanation,
    decorate_related_assumptions_with_governance,
    load_assumptions,
)


REQUIRED_FIELDS = {
    "value",
    "unit",
    "source",
    "owner_role",
    "confidence_impact",
    "review_required",
    "version",
    "effective_date",
    "last_reviewed_at",
    "next_review_due",
    "approval_status",
    "approved_by",
    "approval_role",
    "moc_reference",
}


def _confidence():
    return {
        "sensor_id": "LT-5100",
        "confidence_pct": 42.0,
        "tier": "LOW",
        "sub_scores": {
            "calibration": 0.48,
            "stability": 1.0,
            "cross_sensor": 0.3,
            "physical_plausibility": 1.0,
        },
        "dominant_factor": "cross_sensor",
        "recommended_action": "Cross-check LT-5100 before relying on it.",
        "evidence": [
            {
                "category": "cross_sensor",
                "status": "BAD",
                "severity": "CRITICAL",
                "message": "Flow-implied level contradicts indicated level.",
            },
            {
                "category": "physical_plausibility",
                "status": "OK",
                "severity": "INFO",
                "message": "Reading is within physical envelope.",
            },
        ],
    }


def test_assumption_register_has_required_keys():
    assumptions = load_assumptions()
    expected = {
        "confidence_weights",
        "calibration_interval",
        "mass_balance_tolerance",
        "flow_to_level_conversion_factor",
        "startup_thresholds",
        "stale_reading_threshold",
        "operating_envelopes",
    }

    assert expected.issubset(set(assumptions))
    for assumption_id, assumption in assumptions.items():
        assert REQUIRED_FIELDS.issubset(set(assumption)), assumption_id
    print("  PASS: Assumption register has required governed fields")


def test_confidence_explanation_is_traceable():
    explanation = build_confidence_explanation(
        "LT-5100",
        _confidence(),
        {"sensor_id": "LT-5100", "sensor_type": "level", "value": 50.0, "unit": "ft"},
        load_assumptions(),
    )

    assert explanation["formula"]["expression"].startswith("confidence_pct = 100")
    assert len(explanation["formula"]["terms"]) == 4
    assert explanation["dominant_factor"] == "cross_sensor"
    assert explanation["strongest_evidence"]["category"] == "cross_sensor"
    assert explanation["counter_evidence"][0]["category"] == "physical_plausibility"
    assert "Do not use LT-5100" in explanation["verdict"]
    assert any(item["assumption_id"] == "mass_balance_tolerance" for item in explanation["related_assumptions"])
    assert all("governance_status" in item for item in explanation["related_assumptions"])
    print("  PASS: Confidence explanation is deterministic and assumption-linked")


def test_assumption_governance_summary_is_traceable():
    assumptions = load_assumptions()
    governance = build_assumption_governance(assumptions, now=date(2026, 6, 21))

    assert governance["status"] in {"OK", "WARNING"}
    assert governance["summary"]["total"] == len(assumptions)
    assert governance["summary"]["approved"] >= 1
    assert "generated_at" in governance
    assert governance["policy"]["confidence_score_type"].startswith("governed trust rubric")
    print("  PASS: Governance summary is deterministic and traceable")


def test_assumption_governance_flags_stale_and_unapproved():
    fixture = {
        "stale_threshold": {
            "value": 1,
            "unit": "day",
            "source": "test",
            "owner_role": "Controls Engineer",
            "confidence_impact": "high",
            "review_required": True,
            "version": "1.0",
            "effective_date": "2026-01-01",
            "last_reviewed_at": "2026-01-01",
            "next_review_due": "2026-01-15",
            "approval_status": "approved",
            "approved_by": "Reviewer",
            "approval_role": "Controls Engineer",
            "moc_reference": "TEST-MOC",
        },
        "draft_threshold": {
            "value": 1,
            "unit": "day",
            "source": "test",
            "owner_role": "Controls Engineer",
            "confidence_impact": "medium",
            "review_required": True,
            "version": "1.0",
            "effective_date": "2026-01-01",
            "last_reviewed_at": "2026-01-01",
            "next_review_due": "2026-12-31",
            "approval_status": "draft",
            "approved_by": "",
            "approval_role": "Controls Engineer",
            "moc_reference": "TEST-MOC",
        },
    }
    governance = build_assumption_governance(fixture, now=date(2026, 6, 21))

    assert governance["status"] == "WARNING"
    assert "stale_threshold" in governance["stale_assumption_ids"]
    assert "draft_threshold" in governance["unapproved_assumption_ids"]
    assert any(item["assumption_id"] == "stale_threshold" for item in governance["high_impact_open_items"])
    print("  PASS: Governance flags stale and unapproved assumptions")


def test_related_assumptions_can_be_decorated():
    decorated = decorate_related_assumptions_with_governance([
        {
            "assumption_id": "demo",
            "value": 1,
            "unit": "unit",
            "source": "test",
            "owner_role": "Process Engineer",
            "confidence_impact": "high",
            "review_required": True,
            "version": "1.0",
            "effective_date": "2026-01-01",
            "last_reviewed_at": "2026-06-01",
            "next_review_due": "2026-12-01",
            "approval_status": "approved",
            "approved_by": "Reviewer",
            "approval_role": "Process Engineer",
            "moc_reference": "TEST-MOC",
        }
    ], now=date(2026, 6, 21))

    assert decorated[0]["governance_status"] == "approved"
    assert decorated[0]["moc_reference"] == "TEST-MOC"
    print("  PASS: Related assumptions are decorated for evidence ledgers")


if __name__ == "__main__":
    tests = [
        test_assumption_register_has_required_keys,
        test_confidence_explanation_is_traceable,
        test_assumption_governance_summary_is_traceable,
        test_assumption_governance_flags_stale_and_unapproved,
        test_related_assumptions_can_be_decorated,
    ]

    print("\n" + "=" * 60)
    print("ConfidenceOS -- Assumption Register Tests")
    print("=" * 60 + "\n")

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60 + "\n")

    if failed:
        sys.exit(1)
