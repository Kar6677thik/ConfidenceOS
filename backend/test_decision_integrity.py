"""
test_decision_integrity.py - Tests for lightweight strategic backend helpers.

Run from backend directory:
    python test_decision_integrity.py
"""

import sys
import time

from decision_integrity import (
    annotate_incidents_for_handover,
    build_handover_debt,
    build_score_sensitivity,
    build_trust_dependency_graph,
    update_confidence_debt,
)


def _confidence(sensor_id="LT-5100", tier="LOW", pct=35.0):
    return {
        "sensor_id": sensor_id,
        "tier": tier,
        "confidence_pct": pct,
        "sub_scores": {
            "calibration": 0.5,
            "stability": 1.0,
            "cross_sensor": 0.2,
            "physical_plausibility": 0.8,
        },
        "dominant_factor": "cross_sensor",
        "recommended_action": "Verify locally.",
    }


def test_score_sensitivity():
    result = build_score_sensitivity("LT-5100", _confidence(), role="Engineer")
    assert result["allowed"] is True
    assert len(result["scenarios"]) == 3
    assert any(item["scenario"] == "ignore_mass_balance" for item in result["scenarios"])
    denied = build_score_sensitivity("LT-5100", _confidence(), role="Operator")
    assert denied["allowed"] is False
    print("  PASS: Score sensitivity returns deterministic Engineer scenarios")


def test_confidence_debt_accumulates():
    state = {"LT-5100": {"confidence_debt": 0.0, "last_updated": 100.0, "seconds_below_high": 0.0}}
    output = update_confidence_debt(
        state,
        [_confidence()],
        [{"sensor_id": "LT-5100", "sensor_type": "level"}],
        {"severity": "WARNING"},
        now=3700.0,
    )
    assert output[0]["confidence_debt"] > 0
    assert "predictive" not in output[0]["maintenance_priority"].lower()
    print("  PASS: Confidence debt accumulates without predictive-failure language")


def test_handover_debt_marks_required_items():
    incident = {
        "incident_id": "plant-a:level-integrity",
        "title": "Level integrity suspect",
        "severity": "WARNING",
        "first_action": "Verify level.",
        "action_contract": {"blocked_decisions": ["increase_feed"], "exit_conditions": ["field check"]},
    }
    incidents = annotate_incidents_for_handover([incident])
    token = {
        "token_id": "tok-1",
        "sensor_id": "LT-5100",
        "valid_until": time.time() + 600,
        "valid_until_iso": "soon",
    }
    debt = build_handover_debt("plant-a", incidents, [_confidence()], [token], [], now=time.time())
    types = {item["type"] for item in debt["entries"]}
    assert "unresolved_incident" in types
    assert "active_decision_freeze" in types
    assert "low_confidence_critical_sensor" in types
    assert "active_verification_token" in types
    assert all(item["handover_required"] is True for item in debt["entries"])
    print("  PASS: Handover debt ledger marks unresolved debt")


def test_trust_dependency_graph():
    graph = build_trust_dependency_graph(
        "plant-a",
        [
            {"sensor_id": "LT-5100", "sensor_type": "level", "value": 50, "unit": "ft"},
            {"sensor_id": "FI-2010", "sensor_type": "flow_in", "value": 150, "unit": "gpm"},
            {"sensor_id": "FO-2020", "sensor_type": "flow_out", "value": 80, "unit": "gpm"},
        ],
        [
            _confidence("LT-5100", "LOW", 35.0),
            _confidence("FI-2010", "HIGH", 95.0),
            _confidence("FO-2020", "HIGH", 94.0),
        ],
        {"flags": [], "implied_level": 62.0},
        [{"action_contract": {"blocked_decisions": ["increase_feed"]}}],
    )
    assert any(node["id"] == "implied_level" for node in graph["nodes"])
    assert any(edge["target"] == "feed_increase_decision" for edge in graph["edges"])
    assert "blocked" in graph["summary"].lower()
    print("  PASS: Trust dependency graph connects LT/FI/FO to feed decision")


if __name__ == "__main__":
    tests = [
        test_score_sensitivity,
        test_confidence_debt_accumulates,
        test_handover_debt_marks_required_items,
        test_trust_dependency_graph,
    ]

    print("\n" + "=" * 60)
    print("ConfidenceOS -- Decision Integrity Tests")
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
