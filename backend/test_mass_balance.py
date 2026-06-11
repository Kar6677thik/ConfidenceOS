"""
test_mass_balance.py — Tests for the Mass-Balance Cross-Check Engine (Module 3).

Run from the backend directory with venv activated:
    python test_mass_balance.py
"""

import sys
import time
from mass_balance import (
    MassBalanceEngine,
    MassBalanceFlag,
    MassBalanceState,
    DEFAULT_WINDOW_SECONDS,
    DEFAULT_TOLERANCE,
    SEVERITY_MULTIPLIERS,
    FLOW_TO_LEVEL_RATE,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = ""):
    """Print PASS or FAIL for a test case."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {label}")
    else:
        failed += 1
        msg = f"  FAIL: {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)


def make_reading(sensor_id, sensor_type, value, unit, ts):
    """Create a sensor reading dict matching the simulator format."""
    return {
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": value,
        "unit": unit,
        "timestamp": ts,
        "failure_mode": None,
    }


def make_tick(level, inflow, outflow, ts):
    """Create a full tick of readings (level + flow_in + flow_out)."""
    return [
        make_reading("LT-5100", "level", level, "ft", ts),
        make_reading("FI-2010", "flow_in", inflow, "gpm", ts),
        make_reading("FO-2020", "flow_out", outflow, "gpm", ts),
    ]


# ─── Tests ──────────────────────────────────────────────────────────────────

def test_balanced_flow_no_flags():
    """When inflow == outflow and level is constant, no flags should be raised."""
    engine = MassBalanceEngine()
    t = 1000.0

    # Run 20 ticks at 1 Hz with perfectly balanced flow and constant level
    for i in range(20):
        state = engine.update(make_tick(level=50.0, inflow=100.0, outflow=100.0, ts=t + i))

    check(
        "Balanced flow produces no flags",
        len(state.flags) == 0,
        f"got {len(state.flags)} flags",
    )
    check(
        "Balanced flow has near-zero discrepancy",
        abs(state.discrepancy) < 0.01,
        f"discrepancy = {state.discrepancy:.4f}",
    )


def test_inflow_excess_raises_info():
    """Large inflow excess with constant level should produce an INFO flag."""
    engine = MassBalanceEngine(tolerance=1.0)
    t = 1000.0

    # Run enough ticks so that the cumulative flow-implied delta exceeds tolerance
    # net flow = 200 gpm, level_change_per_sec = 200 * 0.005 = 1.0 ft/s
    # After 3 seconds of trapezoidal integration: ~2.5 ft delta (level stays 50.0)
    for i in range(4):
        state = engine.update(make_tick(level=50.0, inflow=300.0, outflow=100.0, ts=t + i))

    check(
        "Inflow excess raises at least one flag",
        len(state.flags) > 0,
        f"got {len(state.flags)} flags",
    )
    if state.flags:
        check(
            "Flag includes severity string",
            state.flags[0].severity in ("INFO", "WARNING", "CRITICAL"),
            f"severity = {state.flags[0].severity}",
        )


def test_escalation_to_warning():
    """Discrepancy > 2x tolerance should produce WARNING severity."""
    engine = MassBalanceEngine(tolerance=1.0)
    t = 1000.0

    # net flow = 200 gpm → 1.0 ft/s implied level change
    # After ~3s trapezoidal: ~2.5 ft, which > 2.0 (WARNING threshold)
    for i in range(4):
        state = engine.update(make_tick(level=50.0, inflow=300.0, outflow=100.0, ts=t + i))

    has_warning = any(f.severity == "WARNING" for f in state.flags)
    has_critical = any(f.severity == "CRITICAL" for f in state.flags)
    check(
        "Discrepancy > 2x tolerance gives WARNING or higher",
        has_warning or has_critical,
        f"flags: {[f.severity for f in state.flags]}",
    )


def test_escalation_to_critical():
    """Discrepancy > 4x tolerance should produce CRITICAL severity."""
    engine = MassBalanceEngine(tolerance=1.0)
    t = 1000.0

    # net flow = 200 gpm → 1.0 ft/s
    # After ~6s trapezoidal: ~5.0 ft, which > 4.0 (CRITICAL threshold)
    for i in range(7):
        state = engine.update(make_tick(level=50.0, inflow=300.0, outflow=100.0, ts=t + i))

    has_critical = any(f.severity == "CRITICAL" for f in state.flags)
    check(
        "Discrepancy > 4x tolerance gives CRITICAL",
        has_critical,
        f"flags: {[f.severity for f in state.flags]}",
    )


def test_only_highest_severity_reported():
    """The engine should report only the highest severity flag, not all three."""
    engine = MassBalanceEngine(tolerance=1.0)
    t = 1000.0

    # Push discrepancy well past CRITICAL threshold
    for i in range(10):
        state = engine.update(make_tick(level=50.0, inflow=300.0, outflow=100.0, ts=t + i))

    check(
        "Only one flag reported (highest severity)",
        len(state.flags) == 1,
        f"got {len(state.flags)} flags: {[f.severity for f in state.flags]}",
    )
    check(
        "Highest severity is CRITICAL",
        state.flags[0].severity == "CRITICAL",
        f"severity = {state.flags[0].severity}",
    )


def test_reset_clears_state():
    """After reset(), engine should produce a clean state."""
    engine = MassBalanceEngine(tolerance=1.0)
    t = 1000.0

    # Build up some state and flags
    for i in range(10):
        engine.update(make_tick(level=50.0, inflow=300.0, outflow=100.0, ts=t + i))

    engine.reset()

    # After reset, feed balanced flow — should produce no flags
    for i in range(5):
        state = engine.update(make_tick(level=50.0, inflow=100.0, outflow=100.0, ts=2000.0 + i))

    check(
        "Reset clears all flags",
        len(state.flags) == 0,
        f"got {len(state.flags)} flags after reset",
    )
    check(
        "Reset clears discrepancy",
        abs(state.discrepancy) < 0.01,
        f"discrepancy = {state.discrepancy:.4f}",
    )


def test_trapezoidal_integration_accuracy():
    """Trapezoidal integration of constant net flow should be accurate."""
    engine = MassBalanceEngine()
    t = 1000.0

    # Constant 100 gpm net inflow (200 in, 100 out)
    # level_change_rate = 100 * 0.005 = 0.5 ft/s
    # After 10 seconds (trapezoidal): 10 * 0.5 = 5.0 ft (minus first tick is just init)
    num_ticks = 11
    for i in range(num_ticks):
        state = engine.update(make_tick(level=50.0, inflow=200.0, outflow=100.0, ts=t + i))

    expected_delta = 10.0 * 100.0 * FLOW_TO_LEVEL_RATE  # = 5.0 ft
    check(
        f"Trapezoidal integration: implied_delta = {state.implied_delta:.2f} (expected {expected_delta:.2f})",
        abs(state.implied_delta - expected_delta) < 0.01,
        f"diff = {abs(state.implied_delta - expected_delta):.4f}",
    )


def test_outflow_excess_negative_implied_delta():
    """When outflow > inflow, implied_delta should be negative."""
    engine = MassBalanceEngine()
    t = 1000.0

    for i in range(11):
        state = engine.update(make_tick(level=50.0, inflow=100.0, outflow=200.0, ts=t + i))

    check(
        "Outflow excess gives negative implied_delta",
        state.implied_delta < 0,
        f"implied_delta = {state.implied_delta:.2f}",
    )


def test_implied_level_tracks_flow():
    """implied_level should start at the first measured level and track flow deltas."""
    engine = MassBalanceEngine()
    t = 1000.0

    # First tick sets implied_level = measured_level = 50.0
    state = engine.update(make_tick(level=50.0, inflow=200.0, outflow=100.0, ts=t))
    check(
        "Implied level starts at measured level",
        abs(state.implied_level - 50.0) < 0.01,
        f"implied_level = {state.implied_level:.2f}",
    )

    # After 10 more seconds with 100 gpm net: implied += 5.0 ft
    for i in range(1, 11):
        state = engine.update(make_tick(level=50.0, inflow=200.0, outflow=100.0, ts=t + i))

    expected_implied = 50.0 + (10.0 * 100.0 * FLOW_TO_LEVEL_RATE)  # 55.0
    check(
        f"Implied level after 10s of net inflow = {state.implied_level:.2f} (expected {expected_implied:.2f})",
        abs(state.implied_level - expected_implied) < 0.01,
        f"diff = {abs(state.implied_level - expected_implied):.4f}",
    )


def test_missing_sensors_returns_neutral():
    """If any required sensor (level, flow_in, flow_out) is missing, return neutral state."""
    engine = MassBalanceEngine()

    # Only pass level — no flow sensors
    state = engine.update([
        make_reading("LT-5100", "level", 50.0, "ft", 1000.0),
    ])

    check(
        "Missing flow sensors gives neutral state",
        state.discrepancy == 0.0 and len(state.flags) == 0,
        f"discrepancy = {state.discrepancy}, flags = {len(state.flags)}",
    )


def test_to_dict_format():
    """MassBalanceState.to_dict() should have all expected keys."""
    engine = MassBalanceEngine()
    t = 1000.0

    for i in range(5):
        state = engine.update(make_tick(level=50.0, inflow=200.0, outflow=100.0, ts=t + i))

    d = state.to_dict()
    expected_keys = {"implied_level", "measured_level", "discrepancy", "implied_delta", "measured_delta", "flags"}
    check(
        "to_dict() has all expected keys",
        set(d.keys()) == expected_keys,
        f"got keys: {set(d.keys())}",
    )
    check(
        "flags is a list in to_dict()",
        isinstance(d["flags"], list),
        f"flags type = {type(d['flags']).__name__}",
    )


def test_flag_to_dict_format():
    """MassBalanceFlag.to_dict() should have all expected keys."""
    engine = MassBalanceEngine(tolerance=1.0)
    t = 1000.0

    # Force a flag
    for i in range(10):
        state = engine.update(make_tick(level=50.0, inflow=300.0, outflow=100.0, ts=t + i))

    assert len(state.flags) > 0, "Expected at least one flag"
    fd = state.flags[0].to_dict()
    expected_keys = {"severity", "discrepancy", "implied_delta", "measured_delta", "sensor_ids", "message", "timestamp"}
    check(
        "Flag to_dict() has all expected keys",
        set(fd.keys()) == expected_keys,
        f"got keys: {set(fd.keys())}",
    )
    check(
        "Flag message is human-readable string",
        isinstance(fd["message"], str) and len(fd["message"]) > 10,
        f"message = {fd['message'][:50]}...",
    )
    check(
        "Flag sensor_ids lists the involved sensors",
        len(fd["sensor_ids"]) >= 2,
        f"sensor_ids = {fd['sensor_ids']}",
    )


def test_severity_multipliers_match_prd():
    """Severity multipliers should match the PRD spec: INFO=1x, WARNING=2x, CRITICAL=4x."""
    check(
        "INFO multiplier = 1.0",
        SEVERITY_MULTIPLIERS["INFO"] == 1.0,
        f"got {SEVERITY_MULTIPLIERS['INFO']}",
    )
    check(
        "WARNING multiplier = 2.0",
        SEVERITY_MULTIPLIERS["WARNING"] == 2.0,
        f"got {SEVERITY_MULTIPLIERS['WARNING']}",
    )
    check(
        "CRITICAL multiplier = 4.0",
        SEVERITY_MULTIPLIERS["CRITICAL"] == 4.0,
        f"got {SEVERITY_MULTIPLIERS['CRITICAL']}",
    )


def test_default_window_is_15_min():
    """Default integration window should be 900 seconds (15 minutes)."""
    check(
        "Default window = 900 seconds (15 min)",
        DEFAULT_WINDOW_SECONDS == 900.0,
        f"got {DEFAULT_WINDOW_SECONDS}",
    )


# ─── Runner ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("ConfidenceOS -- Module 3: Mass-Balance Cross-Check Tests")
    print("=" * 60)
    print()

    test_balanced_flow_no_flags()
    test_inflow_excess_raises_info()
    test_escalation_to_warning()
    test_escalation_to_critical()
    test_only_highest_severity_reported()
    test_reset_clears_state()
    test_trapezoidal_integration_accuracy()
    test_outflow_excess_negative_implied_delta()
    test_implied_level_tracks_flow()
    test_missing_sensors_returns_neutral()
    test_to_dict_format()
    test_flag_to_dict_format()
    test_severity_multipliers_match_prd()
    test_default_window_is_15_min()

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60)
    print()

    sys.exit(1 if failed > 0 else 0)
