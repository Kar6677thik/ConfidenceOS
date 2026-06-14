"""
test_assumptions.py - Tests for engineering assumptions and confidence explanations.

Run from backend directory:
    python test_assumptions.py
"""

import sys

from assumptions import build_confidence_explanation, load_assumptions


REQUIRED_FIELDS = {
    "value",
    "unit",
    "source",
    "owner_role",
    "confidence_impact",
    "review_required",
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
    print("  PASS: Confidence explanation is deterministic and assumption-linked")


if __name__ == "__main__":
    tests = [
        test_assumption_register_has_required_keys,
        test_confidence_explanation_is_traceable,
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
