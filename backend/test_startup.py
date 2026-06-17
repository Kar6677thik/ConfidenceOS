"""
test_startup.py — Tests for the StartupManager class.

Run from the backend directory with venv activated:
    python test_startup.py
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import time

from startup import StartupManager, StaleReadingFlag


def _make_readings(values: dict[str, float]) -> list[dict]:
    """Helper: build a minimal readings list from {sensor_id: value}."""
    return [{"sensor_id": sid, "value": v} for sid, v in values.items()]


# ─── Basic State Tests ───────────────────────────────────────────────────────

def test_initial_state_is_normal():
    """Default state should be inactive / NORMAL."""
    mgr = StartupManager()
    assert mgr.is_active is False, f"Expected inactive, got {mgr.is_active}"
    assert mgr.mode_name == "NORMAL", f"Expected NORMAL, got {mgr.mode_name}"
    print("  ✓ Initial state is inactive / NORMAL")


def test_activate_sets_startup_mode():
    """activate() should set the manager to STARTUP mode."""
    mgr = StartupManager()
    mgr.activate()
    assert mgr.is_active is True, f"Expected active, got {mgr.is_active}"
    assert mgr.mode_name == "STARTUP", f"Expected STARTUP, got {mgr.mode_name}"
    assert mgr._activated_at is not None, "activated_at should be set"
    print("  ✓ activate() sets STARTUP mode")


def test_deactivate_returns_to_normal():
    """deactivate() should return the manager to NORMAL mode."""
    mgr = StartupManager()
    mgr.activate()
    mgr.deactivate()
    assert mgr.is_active is False, f"Expected inactive, got {mgr.is_active}"
    assert mgr.mode_name == "NORMAL", f"Expected NORMAL, got {mgr.mode_name}"
    assert mgr._activated_at is None, "activated_at should be cleared"
    print("  ✓ deactivate() returns to NORMAL mode")


def test_toggle_on_off():
    """toggle(True/False) should activate/deactivate accordingly."""
    mgr = StartupManager()

    mgr.toggle(True)
    assert mgr.is_active is True, "toggle(True) should activate"
    assert mgr.mode_name == "STARTUP"

    mgr.toggle(False)
    assert mgr.is_active is False, "toggle(False) should deactivate"
    assert mgr.mode_name == "NORMAL"
    print("  ✓ toggle(True/False) works correctly")


# ─── Tier Threshold Tests ────────────────────────────────────────────────────

def test_tier_thresholds_normal():
    """NORMAL thresholds: HIGH=80, MEDIUM=50, LOW=20, CRITICAL=0."""
    mgr = StartupManager()
    expected = {"HIGH": 80, "MEDIUM": 50, "LOW": 20, "CRITICAL": 0}
    actual = mgr.tier_thresholds
    assert actual == expected, f"Expected {expected}, got {actual}"
    print("  ✓ NORMAL tier thresholds are correct")


def test_tier_thresholds_startup():
    """STARTUP thresholds: HIGH=80, MEDIUM=70, LOW=20, CRITICAL=0."""
    mgr = StartupManager()
    mgr.activate()
    expected = {"HIGH": 80, "MEDIUM": 70, "LOW": 20, "CRITICAL": 0}
    actual = mgr.tier_thresholds
    assert actual == expected, f"Expected {expected}, got {actual}"
    print("  ✓ STARTUP tier thresholds are correct (MEDIUM raised to 70)")


# ─── Mass Balance Tolerance Tests ────────────────────────────────────────────

def test_mass_balance_tolerance_normal():
    """In NORMAL mode, mass-balance tolerance multiplier is 1.0."""
    mgr = StartupManager()
    assert mgr.mass_balance_tolerance_multiplier == 1.0, (
        f"Expected 1.0, got {mgr.mass_balance_tolerance_multiplier}"
    )
    print("  ✓ NORMAL mass-balance tolerance multiplier is 1.0")


def test_mass_balance_tolerance_startup():
    """In STARTUP mode, mass-balance tolerance multiplier is 0.5."""
    mgr = StartupManager()
    mgr.activate()
    assert mgr.mass_balance_tolerance_multiplier == 0.5, (
        f"Expected 0.5, got {mgr.mass_balance_tolerance_multiplier}"
    )
    print("  ✓ STARTUP mass-balance tolerance multiplier is 0.5")


# ─── Stale Reading Detection Tests ──────────────────────────────────────────

def test_stale_detection_inactive():
    """Stale detection should return empty list when not in startup mode."""
    mgr = StartupManager()
    readings = _make_readings({"LT-5100": 50.0})
    result = mgr.check_stale_readings(readings, time.time())
    assert result == [], f"Expected empty list, got {result}"
    print("  ✓ Stale detection returns [] when inactive")


def test_stale_detection_under_threshold():
    """No stale flag when reading unchanged for less than 480s."""
    mgr = StartupManager()
    mgr.activate()

    now = 1000.0
    readings = _make_readings({"LT-5100": 50.0})

    # First call: registers the sensor
    mgr.check_stale_readings(readings, now)

    # Second call at 479 seconds later — under threshold
    result = mgr.check_stale_readings(readings, now + 479.0)
    assert len(result) == 0, f"Expected 0 stale flags, got {len(result)}"
    print("  ✓ No stale flag under 480s threshold")


def test_stale_detection_triggers():
    """Stale flag raised when reading unchanged for >= 480s."""
    mgr = StartupManager()
    mgr.activate()

    now = 1000.0
    readings = _make_readings({"LT-5100": 50.0})

    # First call: registers the sensor
    mgr.check_stale_readings(readings, now)

    # Second call at exactly 480 seconds later
    result = mgr.check_stale_readings(readings, now + 480.0)
    assert len(result) == 1, f"Expected 1 stale flag, got {len(result)}"
    assert result[0].sensor_id == "LT-5100"
    assert result[0].duration_seconds == 480.0
    assert result[0].last_value == 50.0
    assert result[0].acknowledged is False
    print("  ✓ Stale flag raised at 480s threshold")


def test_stale_detection_value_change_clears():
    """Changing value should clear the stale flag."""
    mgr = StartupManager()
    mgr.activate()

    now = 1000.0
    readings = _make_readings({"LT-5100": 50.0})

    # Register sensor
    mgr.check_stale_readings(readings, now)

    # Trigger stale
    result = mgr.check_stale_readings(readings, now + 500.0)
    assert len(result) == 1, "Stale flag should exist"

    # Now change the value (delta > 0.01)
    changed_readings = _make_readings({"LT-5100": 55.0})
    result = mgr.check_stale_readings(changed_readings, now + 510.0)
    assert len(result) == 0, f"Expected 0 stale flags after value change, got {len(result)}"
    assert "LT-5100" not in mgr._stale_flags, "Stale flag should be cleared"
    print("  ✓ Value change clears stale flag")


# ─── Acknowledge Tests ───────────────────────────────────────────────────────

def test_acknowledge_stale():
    """Acknowledging a stale flag removes it from active flags."""
    mgr = StartupManager()
    mgr.activate()

    now = 1000.0
    readings = _make_readings({"LT-5100": 50.0})

    # Register then trigger stale
    mgr.check_stale_readings(readings, now)
    mgr.check_stale_readings(readings, now + 500.0)

    # Acknowledge
    result = mgr.acknowledge_stale("LT-5100")
    assert result is True, "acknowledge_stale should return True"
    assert mgr._stale_flags["LT-5100"].acknowledged is True

    # Active (unacknowledged) flags should now be empty
    active = mgr.get_stale_flags()
    assert len(active) == 0, f"Expected 0 active flags after ack, got {len(active)}"
    print("  ✓ Acknowledged stale flag removed from active list")


def test_acknowledge_nonexistent():
    """Acknowledging a non-existent sensor should return False."""
    mgr = StartupManager()
    mgr.activate()
    result = mgr.acknowledge_stale("NONEXISTENT-9999")
    assert result is False, f"Expected False, got {result}"
    print("  ✓ Acknowledging non-existent sensor returns False")


# ─── Serialization Tests ────────────────────────────────────────────────────

def test_to_dict_normal():
    """to_dict() in NORMAL mode should have correct structure."""
    mgr = StartupManager()
    d = mgr.to_dict()

    assert d["mode"] == "NORMAL"
    assert d["is_active"] is False
    assert d["activated_at"] is None
    assert d["tier_thresholds"] == {"HIGH": 80, "MEDIUM": 50, "LOW": 20, "CRITICAL": 0}
    assert d["mass_balance_tolerance_multiplier"] == 1.0
    assert d["stale_threshold_seconds"] is None
    assert d["stale_flags"] == []
    print("  ✓ to_dict() correct in NORMAL mode")


def test_to_dict_startup():
    """to_dict() in STARTUP mode should have correct structure."""
    mgr = StartupManager()
    mgr.activate()
    d = mgr.to_dict()

    assert d["mode"] == "STARTUP"
    assert d["is_active"] is True
    assert d["activated_at"] is not None
    assert d["tier_thresholds"] == {"HIGH": 80, "MEDIUM": 70, "LOW": 20, "CRITICAL": 0}
    assert d["mass_balance_tolerance_multiplier"] == 0.5
    assert d["stale_threshold_seconds"] == 480.0
    assert d["stale_flags"] == []
    print("  ✓ to_dict() correct in STARTUP mode")


# ─── Edge Case Tests ────────────────────────────────────────────────────────

def test_activate_clears_stale_flags():
    """Activating startup mode should clear any old stale state."""
    mgr = StartupManager()
    mgr.activate()

    now = 1000.0
    readings = _make_readings({"LT-5100": 50.0})

    # Register and trigger a stale flag
    mgr.check_stale_readings(readings, now)
    mgr.check_stale_readings(readings, now + 500.0)
    assert len(mgr.get_stale_flags()) == 1, "Should have 1 stale flag"

    # Re-activate — should clear everything
    mgr.activate()
    assert len(mgr.get_stale_flags()) == 0, "Re-activation should clear stale flags"
    assert len(mgr._last_change) == 0, "Re-activation should clear last_change tracking"
    print("  ✓ activate() clears old stale flags and tracking state")


# ─── Runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_initial_state_is_normal,
        test_activate_sets_startup_mode,
        test_deactivate_returns_to_normal,
        test_toggle_on_off,
        test_tier_thresholds_normal,
        test_tier_thresholds_startup,
        test_mass_balance_tolerance_normal,
        test_mass_balance_tolerance_startup,
        test_stale_detection_inactive,
        test_stale_detection_under_threshold,
        test_stale_detection_triggers,
        test_stale_detection_value_change_clears,
        test_acknowledge_stale,
        test_acknowledge_nonexistent,
        test_to_dict_normal,
        test_to_dict_startup,
        test_activate_clears_stale_flags,
    ]

    print(f"\n{'='*60}")
    print("ConfidenceOS — Module 5: Startup Mode Manager Tests")
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
