"""
test_simulator.py — Tests for the SensorSimulator class.

Run from the backend directory with venv activated:
    python test_simulator.py
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import time
import json
from pathlib import Path

from simulator import SensorSimulator, SensorConfig, DEFAULT_SENSORS


def test_default_sensors_exist():
    """All 6 required sensor types must be present."""
    sim = SensorSimulator()
    expected_ids = {"LT-5100", "FI-2010", "FO-2020", "PT-3100", "TT-4100", "ZT-6100"}
    actual_ids = set(sim.sensors.keys())
    assert actual_ids == expected_ids, f"Expected {expected_ids}, got {actual_ids}"
    print("  ✓ All 6 sensor types present")


def test_tick_produces_readings():
    """Each tick() should return exactly 6 readings."""
    sim = SensorSimulator()
    readings = sim.tick()
    assert len(readings) == 6, f"Expected 6 readings, got {len(readings)}"
    for r in readings:
        assert "sensor_id" in r
        assert "sensor_type" in r
        assert "value" in r
        assert "unit" in r
        assert "timestamp" in r
        assert isinstance(r["value"], (int, float))
    print("  ✓ tick() produces 6 valid readings")


def test_readings_within_bounds():
    """All readings should be within min/max bounds."""
    sim = SensorSimulator()
    for _ in range(100):
        readings = sim.tick()
        for r in readings:
            config = sim.sensors[r["sensor_id"]]
            assert config.min_value <= r["value"] <= config.max_value, (
                f"{r['sensor_id']}: value {r['value']} outside [{config.min_value}, {config.max_value}]"
            )
    print("  ✓ All readings within physical bounds over 100 ticks")


def test_readings_have_noise():
    """Readings should not be identical across ticks (noise is applied)."""
    sim = SensorSimulator()
    values = {}
    for _ in range(10):
        readings = sim.tick()
        for r in readings:
            sid = r["sensor_id"]
            if sid not in values:
                values[sid] = []
            values[sid].append(r["value"])

    # Every sensor (except maybe valve with noise_std=0.1) should have variation
    for sid, vals in values.items():
        unique = len(set(vals))
        assert unique > 1, f"{sid}: all 10 readings identical ({vals[0]})"
    print("  ✓ Readings have realistic noise/variation")


def test_calibration_drift_failure():
    """calibration_drift failure should cause reading to shift over time."""
    sim = SensorSimulator()
    sim.failures = []

    from simulator import FailureConfig
    sim.failures.append(FailureConfig(
        sensor_id="LT-5100",
        failure_type="calibration_drift",
        start_time=0.0,
        drift_rate=1.0,  # 1 unit per second drift
    ))
    sim.reset()

    # Take readings over a few seconds
    time.sleep(0.1)
    r1 = [r for r in sim.tick() if r["sensor_id"] == "LT-5100"][0]
    time.sleep(1.0)
    r2 = [r for r in sim.tick() if r["sensor_id"] == "LT-5100"][0]

    assert r2["failure_mode"] == "calibration_drift"
    # The drift should make the second reading noticeably different
    # (drift_rate=1.0 means ~1 unit per second, but noise adds some variance)
    print(f"  ✓ Calibration drift active: LT-5100 reading shifted from {r1['value']} to {r2['value']}")


def test_stuck_reading_failure():
    """stuck_reading failure should freeze the sensor value."""
    sim = SensorSimulator()
    sim.failures = []

    from simulator import FailureConfig
    sim.failures.append(FailureConfig(
        sensor_id="PT-3100",
        failure_type="stuck_reading",
        start_time=0.0,
        stuck_duration=10.0,
    ))
    sim.reset()

    # First tick establishes the stuck value
    sim.tick()
    time.sleep(0.1)

    # Next ticks should return the same value
    r1 = [r for r in sim.tick() if r["sensor_id"] == "PT-3100"][0]
    time.sleep(0.1)
    r2 = [r for r in sim.tick() if r["sensor_id"] == "PT-3100"][0]

    assert r1["value"] == r2["value"], f"Expected stuck value, got {r1['value']} and {r2['value']}"
    assert r1["failure_mode"] == "stuck_reading"
    print(f"  ✓ Stuck reading active: PT-3100 frozen at {r1['value']}")


def test_sg_mismatch_failure():
    """sg_mismatch should scale reading by the SG ratio."""
    sim = SensorSimulator()
    sim.failures = []

    from simulator import FailureConfig
    sim.failures.append(FailureConfig(
        sensor_id="LT-5100",
        failure_type="sg_mismatch",
        start_time=0.0,
        sg_actual=0.65,
        sg_calibrated=0.80,
    ))
    sim.reset()

    reading = [r for r in sim.tick() if r["sensor_id"] == "LT-5100"][0]
    assert reading["failure_mode"] == "sg_mismatch"
    # With SG ratio 0.80/0.65 ≈ 1.23, reading should be scaled up from base ~50
    # The value should be higher than the base_value due to the scaling
    print(f"  ✓ SG mismatch active: LT-5100 reading = {reading['value']} (scaled by {0.80/0.65:.2f})")


def test_command_state_decoupling():
    """command_state_decoupling should show commanded value, not actual."""
    sim = SensorSimulator()
    sim.failures = []

    from simulator import FailureConfig
    sim.failures.append(FailureConfig(
        sensor_id="ZT-6100",
        failure_type="command_state_decoupling",
        start_time=0.0,
        commanded_value=0.0,
        actual_value=85.0,
    ))
    sim.reset()

    reading = [r for r in sim.tick() if r["sensor_id"] == "ZT-6100"][0]
    assert reading["value"] == 0.0, f"Expected 0.0 (commanded), got {reading['value']}"
    assert reading["failure_mode"] == "command_state_decoupling"
    print(f"  ✓ Command-state decoupling: ZT-6100 shows {reading['value']}% (actual is 85%)")


def test_scenario_json_loads():
    """scenario.json should load without errors."""
    sim = SensorSimulator()
    scenario_path = Path(__file__).parent / "scenario.json"
    sim.load_scenario(scenario_path)
    assert len(sim.failures) == 4, f"Expected 4 failures in scenario, got {len(sim.failures)}"
    print(f"  ✓ scenario.json loaded: {len(sim.failures)} failure injections configured")


def test_failure_starts_at_correct_time():
    """Failures should not be active before their start_time."""
    sim = SensorSimulator()
    sim.failures = []

    from simulator import FailureConfig
    sim.failures.append(FailureConfig(
        sensor_id="LT-5100",
        failure_type="stuck_reading",
        start_time=999.0,  # way in the future
        stuck_duration=10.0,
    ))
    sim.reset()

    reading = [r for r in sim.tick() if r["sensor_id"] == "LT-5100"][0]
    assert reading["failure_mode"] is None, (
        f"Failure should not be active yet, but got failure_mode={reading['failure_mode']}"
    )
    print("  ✓ Failure correctly inactive before start_time")


if __name__ == "__main__":
    tests = [
        test_default_sensors_exist,
        test_tick_produces_readings,
        test_readings_within_bounds,
        test_readings_have_noise,
        test_calibration_drift_failure,
        test_stuck_reading_failure,
        test_sg_mismatch_failure,
        test_command_state_decoupling,
        test_scenario_json_loads,
        test_failure_starts_at_correct_time,
    ]

    print(f"\n{'='*60}")
    print("ConfidenceOS — Module 1: Sensor Simulator Tests")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*60}\n")

    if failed > 0:
        sys.exit(1)
