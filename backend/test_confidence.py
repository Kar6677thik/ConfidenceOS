"""
test_confidence.py — Tests for the Confidence Scoring Engine (Module 2).

Run from the backend directory with venv activated:
    python test_confidence.py
"""

import sys
import time
from confidence import (
    ConfidenceEngine,
    ConfidenceWeights,
    _tier_from_pct,
    DEFAULT_CALIBRATION_INTERVAL_DAYS,
)


def make_reading(sensor_id, sensor_type, value, unit="ft", failure_mode=None):
    """Helper to create a reading dict."""
    return {
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": value,
        "unit": unit,
        "timestamp": time.time(),
        "failure_mode": failure_mode,
    }


def make_default_readings(level=50.0, flow_in=120.0, flow_out=118.0,
                           pressure=21.0, temp=350.0, valve=0.0):
    """Create a full set of 6 sensor readings."""
    return [
        make_reading("LT-5100", "level", level, "ft"),
        make_reading("FI-2010", "flow_in", flow_in, "gpm"),
        make_reading("FO-2020", "flow_out", flow_out, "gpm"),
        make_reading("PT-3100", "pressure", pressure, "psi"),
        make_reading("TT-4100", "temperature", temp, "F"),
        make_reading("ZT-6100", "valve", valve, "%"),
    ]


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_tier_classification():
    """Verify tier boundaries match PRD spec."""
    assert _tier_from_pct(100) == "HIGH"
    assert _tier_from_pct(80) == "HIGH"
    assert _tier_from_pct(79.9) == "MEDIUM"
    assert _tier_from_pct(50) == "MEDIUM"
    assert _tier_from_pct(49.9) == "LOW"
    assert _tier_from_pct(20) == "LOW"
    assert _tier_from_pct(19.9) == "CRITICAL"
    assert _tier_from_pct(0) == "CRITICAL"
    print("  PASS: Tier classification matches PRD spec")


def test_texas_city_calibration_score():
    """
    PRD spec: at 47 days uncalibrated with 90-day interval,
    calibration_score should be approximately 0.48.
    """
    engine = ConfidenceEngine(calibration_interval_days=90.0)
    engine.set_calibration_age("LT-5100", 47.0)

    readings = make_default_readings()
    results = engine.score_readings(readings)

    lt_result = next(r for r in results if r.sensor_id == "LT-5100")
    cal_score = lt_result.sub_scores.calibration_score

    # 1 - 47/90 = 0.4778
    expected = 1.0 - (47.0 / 90.0)
    assert abs(cal_score - expected) < 0.01, (
        f"Expected calibration_score ~{expected:.3f}, got {cal_score:.3f}"
    )
    print(f"  PASS: Texas City calibration score = {cal_score:.3f} (expected ~{expected:.3f})")


def test_calibration_score_fresh():
    """A freshly calibrated sensor (0 days) should have score = 1.0."""
    engine = ConfidenceEngine()
    engine.set_calibration_age("LT-5100", 0.0)

    readings = make_default_readings()
    results = engine.score_readings(readings)
    lt_result = next(r for r in results if r.sensor_id == "LT-5100")

    assert lt_result.sub_scores.calibration_score == 1.0
    print("  PASS: Fresh calibration yields score = 1.0")


def test_calibration_score_expired():
    """A sensor past calibration interval should have score = 0.0."""
    engine = ConfidenceEngine(calibration_interval_days=90.0)
    engine.set_calibration_age("LT-5100", 95.0)

    readings = make_default_readings()
    results = engine.score_readings(readings)
    lt_result = next(r for r in results if r.sensor_id == "LT-5100")

    assert lt_result.sub_scores.calibration_score == 0.0
    print("  PASS: Expired calibration yields score = 0.0")


def test_default_weights_sum_to_one():
    """PRD spec: weights must sum to 1.0."""
    w = ConfidenceWeights()
    total = w.calibration + w.stability + w.cross_sensor + w.physical_plausibility
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"
    print(f"  PASS: Default weights sum to {total}")


def test_default_weights_match_prd():
    """PRD spec: default weights [0.30, 0.20, 0.30, 0.20]."""
    w = ConfidenceWeights()
    assert w.calibration == 0.30
    assert w.stability == 0.20
    assert w.cross_sensor == 0.30
    assert w.physical_plausibility == 0.20
    print("  PASS: Default weights match PRD [0.30, 0.20, 0.30, 0.20]")


def test_all_sensors_scored():
    """All 6 sensors should receive a confidence score."""
    engine = ConfidenceEngine()
    readings = make_default_readings()
    results = engine.score_readings(readings)

    assert len(results) == 6, f"Expected 6 results, got {len(results)}"
    scored_ids = {r.sensor_id for r in results}
    expected_ids = {"LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100", "ZT-6100"}
    assert scored_ids == expected_ids
    print("  PASS: All 6 sensors scored")


def test_healthy_sensors_high_confidence():
    """Normal readings with fresh calibration should be HIGH confidence."""
    engine = ConfidenceEngine()
    # All sensors freshly calibrated
    for sid in ["LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100", "ZT-6100"]:
        engine.set_calibration_age(sid, 0.0)

    readings = make_default_readings()
    results = engine.score_readings(readings)

    for r in results:
        assert r.confidence_pct >= 80.0, (
            f"{r.sensor_id}: expected HIGH confidence, got {r.confidence_pct}% ({r.tier})"
        )
    print("  PASS: Healthy sensors all have HIGH confidence")


def test_reason_strings_present():
    """Degraded sensors should have non-empty reason strings."""
    engine = ConfidenceEngine(calibration_interval_days=90.0)
    engine.set_calibration_age("LT-5100", 47.0)

    readings = make_default_readings()
    results = engine.score_readings(readings)

    lt_result = next(r for r in results if r.sensor_id == "LT-5100")
    assert len(lt_result.reasons) > 0, "Expected reason strings for degraded sensor"
    assert any("Calibration" in r for r in lt_result.reasons)
    print(f"  PASS: Reason string present: '{lt_result.reasons[0]}'")


def test_physical_plausibility_out_of_envelope():
    """A reading outside the operating envelope should degrade plausibility score."""
    engine = ConfidenceEngine()
    for sid in ["LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100", "ZT-6100"]:
        engine.set_calibration_age(sid, 0.0)

    # Level at 180 ft is outside normal envelope (5-150)
    readings = make_default_readings(level=180.0)
    results = engine.score_readings(readings)

    lt_result = next(r for r in results if r.sensor_id == "LT-5100")
    phys = lt_result.sub_scores.physical_plausibility_score
    assert phys < 1.0, f"Expected plausibility < 1.0 for out-of-envelope reading, got {phys}"
    assert any("Plausibility" in r for r in lt_result.reasons)
    print(f"  PASS: Out-of-envelope reading (180 ft) has plausibility = {phys:.3f}")


def test_to_dict_format():
    """The to_dict() output should have all expected keys."""
    engine = ConfidenceEngine()
    readings = make_default_readings()
    results = engine.score_readings(readings)

    d = results[0].to_dict()
    assert "sensor_id" in d
    assert "confidence_pct" in d
    assert "tier" in d
    assert "sub_scores" in d
    assert "reasons" in d
    assert "calibration" in d["sub_scores"]
    assert "stability" in d["sub_scores"]
    assert "cross_sensor" in d["sub_scores"]
    assert "physical_plausibility" in d["sub_scores"]
    assert "evidence" in d
    assert "namur_state" in d
    assert "recommended_action" in d
    assert "dominant_factor" in d
    print("  PASS: to_dict() format has all expected keys")


def test_evidence_for_calibration_degradation():
    """Calibration degradation should produce structured evidence and action."""
    engine = ConfidenceEngine(calibration_interval_days=90.0)
    engine.set_calibration_age("LT-5100", 47.0)

    readings = make_default_readings()
    results = engine.score_readings(readings)
    lt_result = next(r for r in results if r.sensor_id == "LT-5100").to_dict()

    calibration = next(e for e in lt_result["evidence"] if e["category"] == "calibration")
    assert calibration["status"] in ("DEGRADED", "BAD")
    assert "calibration" in calibration["action"].lower()
    assert lt_result["dominant_factor"] == "calibration"
    assert "calibration" in lt_result["recommended_action"].lower()
    print("  PASS: Calibration degradation creates structured evidence and action")


def test_evidence_for_physical_plausibility():
    """Out-of-envelope values should produce physical plausibility evidence."""
    engine = ConfidenceEngine()
    readings = make_default_readings(level=180.0)
    results = engine.score_readings(readings)
    lt_result = next(r for r in results if r.sensor_id == "LT-5100").to_dict()

    plausibility = next(e for e in lt_result["evidence"] if e["category"] == "physical_plausibility")
    assert plausibility["status"] != "OK"
    assert "outside normal envelope" in plausibility["message"]
    assert "physically possible" in lt_result["recommended_action"]
    print("  PASS: Physical plausibility evidence explains out-of-envelope values")


def test_stability_score_stuck_detection():
    """Repeated identical readings should degrade stability score."""
    engine = ConfidenceEngine()
    for sid in ["LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100", "ZT-6100"]:
        engine.set_calibration_age(sid, 0.0)

    # Feed many identical readings for PT-3100 (stuck at 21.0)
    base_time = time.time()
    for i in range(40):
        readings = [
            {"sensor_id": "LT-5100", "sensor_type": "level", "value": 50.0 + i * 0.1,
             "unit": "ft", "timestamp": base_time + i, "failure_mode": None},
            {"sensor_id": "FI-2010", "sensor_type": "flow_in", "value": 120.0 + i * 0.1,
             "unit": "gpm", "timestamp": base_time + i, "failure_mode": None},
            {"sensor_id": "FO-2020", "sensor_type": "flow_out", "value": 118.0 + i * 0.1,
             "unit": "gpm", "timestamp": base_time + i, "failure_mode": None},
            {"sensor_id": "PT-3100", "sensor_type": "pressure", "value": 21.0,  # STUCK
             "unit": "psi", "timestamp": base_time + i, "failure_mode": None},
            {"sensor_id": "TT-4100", "sensor_type": "temperature", "value": 350.0 + i * 0.1,
             "unit": "F", "timestamp": base_time + i, "failure_mode": None},
            {"sensor_id": "ZT-6100", "sensor_type": "valve", "value": 0.0 + i * 0.001,
             "unit": "%", "timestamp": base_time + i, "failure_mode": None},
        ]
        results = engine.score_readings(readings)

    pt_result = next(r for r in results if r.sensor_id == "PT-3100")
    stab = pt_result.sub_scores.stability_score
    assert stab < 1.0, f"Expected stability < 1.0 for stuck sensor, got {stab}"
    print(f"  PASS: Stuck sensor PT-3100 stability = {stab:.3f}")


if __name__ == "__main__":
    tests = [
        test_tier_classification,
        test_texas_city_calibration_score,
        test_calibration_score_fresh,
        test_calibration_score_expired,
        test_default_weights_sum_to_one,
        test_default_weights_match_prd,
        test_all_sensors_scored,
        test_healthy_sensors_high_confidence,
        test_reason_strings_present,
        test_physical_plausibility_out_of_envelope,
        test_to_dict_format,
        test_evidence_for_calibration_degradation,
        test_evidence_for_physical_plausibility,
        test_stability_score_stuck_detection,
    ]

    print(f"\n{'='*60}")
    print("ConfidenceOS -- Module 2: Confidence Scoring Engine Tests")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*60}\n")

    if failed > 0:
        sys.exit(1)
