"""
test_mode_inference.py - Tests for deterministic operating-mode inference.

Run from backend directory:
    python test_mode_inference.py
"""

import sys

from mode_inference import ModeInferenceEngine


def _reading(sensor_id, sensor_type, value, ts):
    return {
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": value,
        "unit": "",
        "timestamp": ts,
    }


def _confidence(sensor_id="LT-5100", tier="HIGH", pct=95.0):
    return {"sensor_id": sensor_id, "tier": tier, "confidence_pct": pct}


def test_steady_state():
    engine = ModeInferenceEngine()
    result = engine.infer(
        readings=[_reading("LT-5100", "level", 50, 1)],
        confidence=[_confidence()],
        mass_balance={"flags": []},
        startup_mode={"is_active": False},
        stale_flags=[],
    )

    assert result["mode"] == "STEADY_STATE"
    print("  PASS: Nominal evidence infers STEADY_STATE")


def test_startup_ramp_from_manual_mode():
    engine = ModeInferenceEngine()
    result = engine.infer(
        readings=[_reading("FI-2010", "flow_in", 120, 1)],
        confidence=[_confidence("FI-2010")],
        mass_balance={"flags": []},
        startup_mode={"is_active": True},
        stale_flags=[],
    )

    assert result["mode"] == "STARTUP_RAMP"
    assert result["evidence"]["manual_startup_active"] is True
    print("  PASS: Manual startup state infers STARTUP_RAMP")


def test_mass_balance_takes_priority_over_startup():
    engine = ModeInferenceEngine()
    result = engine.infer(
        readings=[_reading("LT-5100", "level", 50, 1)],
        confidence=[_confidence()],
        mass_balance={"flags": [{"severity": "WARNING", "sensor_ids": ["LT-5100"]}]},
        startup_mode={"is_active": True},
        stale_flags=[],
    )

    assert result["mode"] == "MASS_BALANCE_DIVERGENCE"
    assert "Startup" in result["reasons"][-1]
    print("  PASS: Mass-balance divergence takes priority over startup")


def test_manual_verification_for_stale_reading():
    engine = ModeInferenceEngine()
    result = engine.infer(
        readings=[_reading("PT-3100", "pressure", 20, 1)],
        confidence=[_confidence("PT-3100")],
        mass_balance={"flags": []},
        startup_mode={"is_active": True},
        stale_flags=[{"sensor_id": "PT-3100", "duration_seconds": 600}],
    )

    assert result["mode"] == "MANUAL_VERIFICATION_REQUIRED"
    assert result["priority_sensors"] == ["PT-3100"]
    print("  PASS: Stale reading infers MANUAL_VERIFICATION_REQUIRED")


def test_instrumentation_suspect():
    engine = ModeInferenceEngine()
    result = engine.infer(
        readings=[_reading("TT-4100", "temperature", 350, 1)],
        confidence=[_confidence("TT-4100", "MEDIUM", 65)],
        mass_balance={"flags": []},
        startup_mode={"is_active": False},
        stale_flags=[],
    )

    assert result["mode"] == "INSTRUMENTATION_SUSPECT"
    print("  PASS: Degraded confidence infers INSTRUMENTATION_SUSPECT")


if __name__ == "__main__":
    tests = [
        test_steady_state,
        test_startup_ramp_from_manual_mode,
        test_mass_balance_takes_priority_over_startup,
        test_manual_verification_for_stale_reading,
        test_instrumentation_suspect,
    ]

    print("\n" + "=" * 60)
    print("ConfidenceOS -- Mode Inference Tests")
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
