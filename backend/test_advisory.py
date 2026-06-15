"""
test_advisory.py - Tests for advisory context and incident fusion.

Run from backend directory:
    python test_advisory.py
"""

import sys

from advisory import detect_plant_context, build_incidents, build_timeline_events


def _reading(sensor_id="LT-5100", sensor_type="level", value=50.0):
    return {"sensor_id": sensor_id, "sensor_type": sensor_type, "value": value, "unit": "ft"}


def _confidence(sensor_id="LT-5100", tier="HIGH", pct=95.0):
    return {
        "sensor_id": sensor_id,
        "tier": tier,
        "confidence_pct": pct,
        "reasons": ["Calibration: 47 days elapsed."],
        "recommended_action": f"Verify calibration record for {sensor_id}.",
        "evidence": [
            {
                "category": "calibration",
                "status": "DEGRADED" if tier != "HIGH" else "OK",
                "severity": "WARNING" if tier != "HIGH" else "INFO",
                "message": "Calibration evidence",
            }
        ],
    }


def test_nominal_context_has_no_incidents():
    readings = [_reading()]
    confidence = [_confidence()]
    mb = {"flags": [], "discrepancy": 0.1}
    context = detect_plant_context(readings, confidence, mb, {"is_active": False}, [])
    incidents = build_incidents("plant-a", readings, confidence, mb, [], context)

    assert context["state"] == "STEADY_STATE"
    assert incidents == []
    print("  PASS: Nominal state has steady context and no incidents")


def test_level_integrity_fusion():
    readings = [_reading()]
    confidence = [_confidence(tier="LOW", pct=35.0)]
    mb = {"flags": [{"severity": "WARNING", "message": "Level and flow diverge."}], "discrepancy": 12.5}
    context = detect_plant_context(readings, confidence, mb, {"is_active": False}, [])
    incidents = build_incidents("plant-a", readings, confidence, mb, [], context)

    assert context["state"] == "MASS_BALANCE_DIVERGENCE"
    assert incidents[0]["incident_id"] == "plant-a:level-integrity"
    # first_action is sourced from the asset model's operator_single_safe_move
    assert incidents[0]["first_action"], "first_action should be non-empty"
    assert incidents[0]["action_contract"]["do_not_use"] == ["LT-5100"]
    # Blocked decisions come from the asset model when defined
    blocked = incidents[0]["action_contract"]["blocked_decisions"]
    assert len(blocked) > 0, f"Expected at least one blocked decision, got: {blocked}"
    print("  PASS: Level confidence plus mass-balance flag fuses into one incident")


def test_alarm_collapse_inventory_startup():
    readings = [
        _reading("LT-5100", "level", 52.0),
        _reading("FI-2010", "flow_in", 140.0),
        _reading("FO-2020", "flow_out", 80.0),
    ]
    confidence = [_confidence(tier="LOW", pct=35.0)]
    mb = {
        "flags": [{"severity": "WARNING", "message": "Level and flow diverge.", "sensor_ids": ["LT-5100", "FI-2010", "FO-2020"]}],
        "discrepancy": 12.5,
    }
    inferred = {
        "mode": "MASS_BALANCE_DIVERGENCE",
        "severity": "WARNING",
        "reasons": ["Startup or ramping evidence is also active."],
        "priority_sensors": ["LT-5100"],
        "layout_hint": "promote_mass_balance",
        "operator_focus": "Mass-balance divergence active.",
    }
    context = detect_plant_context(readings, confidence, mb, {"is_active": True}, [], inferred_mode=inferred)
    incidents = build_incidents("plant-a", readings, confidence, mb, [], context)

    assert len(incidents) == 1
    assert incidents[0]["title"] == "Inventory accumulation with unreliable level indication"
    assert incidents[0]["alarm_collapse"]["collapsed"] is True
    assert "mass_balance_divergence" in incidents[0]["alarm_collapse"]["consumed_alarm_types"]
    assert "FI-2010" in incidents[0]["action_contract"]["trusted_substitutes"]
    print("  PASS: Alarm collapse creates one inventory abnormal situation")


def test_startup_stale_incident():
    readings = [_reading("PT-3100", "pressure", 21.0)]
    confidence = [_confidence("PT-3100")]
    mb = {"flags": [], "discrepancy": 0}
    stale = [{"sensor_id": "PT-3100", "duration_seconds": 600}]
    context = detect_plant_context(readings, confidence, mb, {"is_active": True}, stale)
    incidents = build_incidents("plant-a", readings, confidence, mb, stale, context)

    assert context["state"] == "STARTUP"
    assert any(i["incident_id"] == "plant-a:startup-verification" for i in incidents)
    print("  PASS: Startup stale flag creates verification incident")


def test_multiple_degraded_sensors_incident():
    readings = [
        _reading("FI-2010", "flow_in", 120.0),
        _reading("TT-4100", "temperature", 350.0),
    ]
    confidence = [
        _confidence("FI-2010", "MEDIUM", 65.0),
        _confidence("TT-4100", "LOW", 45.0),
    ]
    mb = {"flags": [], "discrepancy": 0}
    context = detect_plant_context(readings, confidence, mb, {"is_active": False}, [])
    incidents = build_incidents("plant-a", readings, confidence, mb, [], context)

    assert context["state"] == "INSTRUMENTATION_SUSPECT"
    assert incidents[0]["incident_id"] == "plant-a:instrument-confidence"
    assert "TT-4100" in incidents[0]["summary"]
    print("  PASS: Multiple degraded sensors create confidence incident")


def test_timeline_events_include_contract_and_freeze():
    readings = [_reading()]
    confidence = [_confidence(tier="LOW", pct=35.0)]
    mb = {"flags": [{"severity": "WARNING", "message": "Level and flow diverge."}], "discrepancy": 12.5}
    inferred = {"mode": "MASS_BALANCE_DIVERGENCE", "severity": "WARNING", "rule_id": "test", "reasons": []}
    context = detect_plant_context(readings, confidence, mb, {"is_active": False}, [], inferred_mode=inferred)
    incidents = build_incidents("plant-a", readings, confidence, mb, [], context)
    events = build_timeline_events("plant-a", inferred, confidence, mb, incidents, timestamp=123.0)
    event_types = {event["event_type"] for event in events}

    assert "mode_detected" in event_types
    assert "confidence_degraded" in event_types
    assert "mass_balance_divergence" in event_types
    assert "action_contract_created" in event_types
    assert "decision_freeze_created" in event_types
    print("  PASS: Timeline events include mode, confidence, mass-balance, contract, and freeze")


if __name__ == "__main__":
    tests = [
        test_nominal_context_has_no_incidents,
        test_level_integrity_fusion,
        test_alarm_collapse_inventory_startup,
        test_startup_stale_incident,
        test_multiple_degraded_sensors_incident,
        test_timeline_events_include_contract_and_freeze,
    ]

    print("\n" + "=" * 60)
    print("ConfidenceOS -- Advisory Engine Tests")
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
