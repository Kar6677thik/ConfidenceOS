"""
test_advisory.py - Tests for advisory context and incident fusion.

Run from backend directory:
    python test_advisory.py
"""

import sys

from advisory import detect_plant_context, build_incidents


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
    assert "sight glass" in incidents[0]["first_action"]
    print("  PASS: Level confidence plus mass-balance flag fuses into one incident")


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


if __name__ == "__main__":
    tests = [
        test_nominal_context_has_no_incidents,
        test_level_integrity_fusion,
        test_startup_stale_incident,
        test_multiple_degraded_sensors_incident,
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
