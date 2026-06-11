"""
test_handover.py — Tests for the Shift Handover Brief Generator (Module 6).

Run from the backend directory with venv activated:
    python test_handover.py
"""

import sys
import os
import time
import asyncio
from datetime import datetime, timezone

from handover import HandoverBriefGenerator


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_confidence_entry(sensor_id, confidence_pct, tier, reasons=None):
    """Helper to create a confidence result dict (mimics ConfidenceEngine output)."""
    return {
        "sensor_id": sensor_id,
        "confidence_pct": confidence_pct,
        "tier": tier,
        "reasons": reasons or [],
    }


def _make_mass_balance(implied=None, measured=None, discrepancy=None,
                       implied_delta=None, measured_delta=None, flags=None):
    """Helper to create a mass-balance state dict."""
    return {
        "implied_level": implied,
        "measured_level": measured,
        "discrepancy": discrepancy,
        "implied_delta": implied_delta,
        "measured_delta": measured_delta,
        "flags": flags or [],
    }


def _make_mode_state(mode="NORMAL", stale_flags=None):
    """Helper to create a mode state dict."""
    return {
        "mode": mode,
        "stale_flags": stale_flags or [],
    }


def _make_anomaly(sensor_id, severity="WARNING", description="Spike detected",
                  anomaly_type="spike"):
    """Helper to create an anomaly dict."""
    return {
        "sensor_id": sensor_id,
        "severity": severity,
        "description": description,
        "anomaly_type": anomaly_type,
        "timestamp": time.time(),
    }


def _healthy_state():
    """All-healthy, no-issues system state for baseline tests."""
    confidence_data = [
        _make_confidence_entry("LT-5100", 95.0, "HIGH"),
        _make_confidence_entry("FI-2010", 92.0, "HIGH"),
        _make_confidence_entry("FO-2020", 88.0, "HIGH"),
        _make_confidence_entry("PT-3100", 91.0, "HIGH"),
        _make_confidence_entry("TT-4100", 90.0, "HIGH"),
        _make_confidence_entry("ZT-6100", 85.0, "HIGH"),
    ]
    mb = _make_mass_balance(implied=50.0, measured=50.2, discrepancy=0.2)
    mode = _make_mode_state()
    gen = HandoverBriefGenerator()
    return gen.collect_system_state(confidence_data, mb, [], mode)


def _degraded_state():
    """State with 2 degraded sensors (LOW + CRITICAL)."""
    confidence_data = [
        _make_confidence_entry("LT-5100", 30.0, "LOW",
                               ["Calibration overdue", "Stability degraded"]),
        _make_confidence_entry("FI-2010", 10.0, "CRITICAL",
                               ["Sensor failure suspected"]),
        _make_confidence_entry("FO-2020", 88.0, "HIGH"),
        _make_confidence_entry("PT-3100", 91.0, "HIGH"),
        _make_confidence_entry("TT-4100", 90.0, "HIGH"),
        _make_confidence_entry("ZT-6100", 85.0, "HIGH"),
    ]
    mb = _make_mass_balance(implied=50.0, measured=50.2, discrepancy=0.2)
    mode = _make_mode_state()
    gen = HandoverBriefGenerator()
    return gen.collect_system_state(confidence_data, mb, [], mode)


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_collect_system_state_structure():
    """Verify all required keys are present in the collected state dict."""
    state = _healthy_state()
    required_keys = [
        "timestamp", "generated_at", "mode", "total_sensors",
        "healthy_sensors", "degraded_sensors", "mass_balance",
        "anomalies", "stale_flags",
    ]
    for key in required_keys:
        assert key in state, f"Missing key '{key}' in system state"
    # mass_balance sub-keys
    mb_keys = ["implied_level", "measured_level", "discrepancy",
               "implied_delta", "measured_delta", "flags"]
    for key in mb_keys:
        assert key in state["mass_balance"], f"Missing key '{key}' in mass_balance"
    print("  PASS: collect_system_state has all required keys")


def test_collect_state_counts_degraded_sensors():
    """Verify degraded vs healthy counting is correct."""
    confidence_data = [
        _make_confidence_entry("LT-5100", 30.0, "LOW"),
        _make_confidence_entry("FI-2010", 10.0, "CRITICAL"),
        _make_confidence_entry("FO-2020", 60.0, "MEDIUM"),
        _make_confidence_entry("PT-3100", 91.0, "HIGH"),
        _make_confidence_entry("TT-4100", 90.0, "HIGH"),
        _make_confidence_entry("ZT-6100", 85.0, "HIGH"),
    ]
    mb = _make_mass_balance()
    mode = _make_mode_state()
    gen = HandoverBriefGenerator()
    state = gen.collect_system_state(confidence_data, mb, [], mode)

    assert state["total_sensors"] == 6, f"Expected 6 total, got {state['total_sensors']}"
    assert state["healthy_sensors"] == 3, f"Expected 3 healthy, got {state['healthy_sensors']}"
    assert len(state["degraded_sensors"]) == 3, (
        f"Expected 3 degraded, got {len(state['degraded_sensors'])}"
    )
    print("  PASS: Degraded vs healthy counting is correct")


def test_collect_state_limits_anomalies():
    """Verify anomaly list is capped at 20."""
    confidence_data = [_make_confidence_entry("LT-5100", 95.0, "HIGH")]
    mb = _make_mass_balance()
    mode = _make_mode_state()
    anomalies = [_make_anomaly(f"S-{i}") for i in range(30)]

    gen = HandoverBriefGenerator()
    state = gen.collect_system_state(confidence_data, mb, anomalies, mode)

    assert len(state["anomalies"]) == 20, (
        f"Expected 20 anomalies (capped), got {len(state['anomalies'])}"
    )
    # Should keep the LAST 20
    assert state["anomalies"][0]["sensor_id"] == "S-10"
    assert state["anomalies"][-1]["sensor_id"] == "S-29"
    print("  PASS: Anomaly list correctly capped at 20 (last 20 kept)")


def test_fallback_brief_no_issues():
    """All healthy, no flags — brief should have no concerns."""
    gen = HandoverBriefGenerator()
    state = _healthy_state()
    brief = gen._fallback_brief(state)

    assert "No mass-balance inconsistencies" in brief["brief"] or \
           "No immediate concerns" in brief["brief"], \
        "Expected clean status message in brief"
    assert "DEGRADED SENSORS" in brief["brief"]
    assert "None — all sensors at HIGH confidence" in brief["brief"]
    assert "No anomalies recorded" in brief["brief"]
    assert "No specific actions required" in brief["brief"]
    print("  PASS: Fallback brief for healthy state contains expected sections")


def test_fallback_brief_degraded_sensors():
    """Brief includes degraded sensor details when sensors are degraded."""
    gen = HandoverBriefGenerator()
    state = _degraded_state()
    brief = gen._fallback_brief(state)

    assert "LT-5100" in brief["brief"], "Expected degraded sensor LT-5100 in brief"
    assert "FI-2010" in brief["brief"], "Expected degraded sensor FI-2010 in brief"
    assert "30.0%" in brief["brief"] or "30%" in brief["brief"], \
        "Expected confidence percentage for LT-5100"
    assert "CRITICAL" in brief["brief"], "Expected CRITICAL tier in brief"
    assert "LOW" in brief["brief"], "Expected LOW tier in brief"
    print("  PASS: Fallback brief includes degraded sensor details")


def test_fallback_brief_mass_balance_flags():
    """Brief includes mass-balance flag info when flags are present."""
    confidence_data = [_make_confidence_entry("LT-5100", 95.0, "HIGH")]
    flags = [{"severity": "WARNING", "message": "Level/flow discrepancy > 2 ft"}]
    mb = _make_mass_balance(implied=50.0, measured=53.0, discrepancy=3.0, flags=flags)
    mode = _make_mode_state()

    gen = HandoverBriefGenerator()
    state = gen.collect_system_state(confidence_data, mb, [], mode)
    brief = gen._fallback_brief(state)

    assert "Level/flow discrepancy" in brief["brief"], \
        "Expected flag message in brief"
    assert "WARNING" in brief["brief"], "Expected severity in brief"
    assert "mass-balance inconsistency" in brief["brief"].lower() or \
           "mass-balance" in brief["brief"].lower(), \
        "Expected mass-balance mention in overall status"
    print("  PASS: Fallback brief includes mass-balance flag info")


def test_fallback_brief_with_anomalies():
    """Brief includes anomaly section when anomalies exist."""
    confidence_data = [_make_confidence_entry("LT-5100", 95.0, "HIGH")]
    mb = _make_mass_balance()
    mode = _make_mode_state()
    anomalies = [
        _make_anomaly("PT-3100", "WARNING", "Sudden pressure spike"),
        _make_anomaly("TT-4100", "INFO", "Temperature drift"),
    ]

    gen = HandoverBriefGenerator()
    state = gen.collect_system_state(confidence_data, mb, anomalies, mode)
    brief = gen._fallback_brief(state)

    assert "ANOMALIES THIS SHIFT" in brief["brief"]
    assert "PT-3100" in brief["brief"]
    assert "TT-4100" in brief["brief"]
    assert "Sudden pressure spike" in brief["brief"]
    assert "2 events" in brief["brief"]
    print("  PASS: Fallback brief includes anomaly section")


def test_fallback_brief_with_stale_flags():
    """Brief includes stale reading info when stale flags exist."""
    confidence_data = [_make_confidence_entry("LT-5100", 95.0, "HIGH")]
    mb = _make_mass_balance()
    stale = [{"sensor_id": "PT-3100", "duration_seconds": 120.0}]
    mode = _make_mode_state(mode="STARTUP", stale_flags=stale)

    gen = HandoverBriefGenerator()
    state = gen.collect_system_state(confidence_data, mb, [], mode)
    brief = gen._fallback_brief(state)

    assert "PT-3100" in brief["brief"]
    assert "stuck" in brief["brief"].lower() or "unchanged" in brief["brief"].lower(), \
        "Expected stale/stuck warning in brief"
    assert "120" in brief["brief"], "Expected duration in brief"
    print("  PASS: Fallback brief includes stale reading info")


def test_fallback_brief_recommended_actions_critical():
    """MANDATORY action for CRITICAL-tier sensors."""
    gen = HandoverBriefGenerator()
    state = _degraded_state()  # Contains FI-2010 at CRITICAL
    brief = gen._fallback_brief(state)

    assert "MANDATORY" in brief["brief"], \
        "Expected MANDATORY action for CRITICAL sensor"
    assert "FI-2010" in brief["brief"]
    assert "sight glass" in brief["brief"].lower() or \
           "field transmitter" in brief["brief"].lower(), \
        "Expected manual verification instruction for CRITICAL sensor"
    print("  PASS: CRITICAL sensor gets MANDATORY recommended action")


def test_fallback_brief_recommended_actions_low():
    """Cross-verify action for LOW-tier sensors."""
    gen = HandoverBriefGenerator()
    state = _degraded_state()  # Contains LT-5100 at LOW
    brief = gen._fallback_brief(state)

    assert "Cross-verify" in brief["brief"], \
        "Expected cross-verify action for LOW sensor"
    assert "LT-5100" in brief["brief"]
    assert "calibration" in brief["brief"].lower(), \
        "Expected calibration recommendation for LOW sensor"
    print("  PASS: LOW sensor gets cross-verify recommended action")


def test_fallback_brief_source_is_fallback():
    """Source field says 'fallback' for template-generated briefs."""
    gen = HandoverBriefGenerator()
    state = _healthy_state()
    brief = gen._fallback_brief(state)

    assert brief["source"] == "fallback", \
        f"Expected source='fallback', got '{brief['source']}'"
    assert brief["model"] is None, \
        f"Expected model=None for fallback, got '{brief['model']}'"
    print("  PASS: Fallback brief source is 'fallback' with model=None")


def test_build_user_message_format():
    """Verify Claude prompt is well-formed with expected sections."""
    gen = HandoverBriefGenerator()
    confidence_data = [
        _make_confidence_entry("LT-5100", 30.0, "LOW",
                               ["Calibration overdue"]),
        _make_confidence_entry("FI-2010", 92.0, "HIGH"),
    ]
    flags = [{"severity": "WARNING", "message": "Level mismatch"}]
    mb = _make_mass_balance(implied=50.0, measured=53.0, discrepancy=3.0, flags=flags)
    anomalies = [_make_anomaly("PT-3100", "WARNING", "Pressure spike")]
    stale = [{"sensor_id": "TT-4100", "duration_seconds": 60.0}]
    mode = _make_mode_state(mode="STARTUP", stale_flags=stale)

    state = gen.collect_system_state(confidence_data, mb, anomalies, mode)
    message = gen._build_user_message(state)

    assert "Generate a shift handover brief" in message
    assert "Current mode: STARTUP" in message
    assert "SENSOR CONFIDENCE STATUS (2 sensors)" in message
    assert "Healthy (HIGH confidence): 1" in message
    assert "Degraded: 1" in message
    assert "LT-5100: 30.0% (LOW)" in message
    assert "Calibration overdue" in message
    assert "MASS-BALANCE STATUS:" in message
    assert "Implied level (from flows): 50.0 ft" in message
    assert "FLAG [WARNING]: Level mismatch" in message
    assert "ANOMALIES DURING SHIFT" in message
    assert "PT-3100" in message
    assert "STALE READING FLAGS" in message
    assert "TT-4100" in message
    assert "60s" in message
    print("  PASS: User message is well-formed with all expected sections")


def test_generate_brief_uses_fallback_without_key():
    """No API key → fallback path is used."""
    # Ensure no API key is set
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        gen = HandoverBriefGenerator()
        state = _healthy_state()
        brief = asyncio.run(gen.generate_brief(state))

        assert brief["source"] == "fallback", \
            f"Expected fallback source, got '{brief['source']}'"
        assert brief["brief"], "Expected non-empty brief text"
        assert "generated_at" in brief
        assert "system_state_summary" in brief
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original
    print("  PASS: generate_brief uses fallback when no API key is set")


def test_latest_brief_initially_none():
    """latest_brief starts as None for a fresh generator."""
    gen = HandoverBriefGenerator()
    assert gen.latest_brief is None, \
        f"Expected latest_brief=None, got {gen.latest_brief}"
    assert gen.latest_timestamp is None, \
        f"Expected latest_timestamp=None, got {gen.latest_timestamp}"
    print("  PASS: latest_brief and latest_timestamp are initially None")


def test_latest_brief_updated_after_generate():
    """latest_brief is updated after calling generate_brief."""
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        gen = HandoverBriefGenerator()
        assert gen.latest_brief is None

        state = _healthy_state()
        brief = asyncio.run(gen.generate_brief(state))

        assert gen.latest_brief is not None, "latest_brief should not be None after generate"
        assert gen.latest_brief is brief, "latest_brief should be the returned brief object"
        assert gen.latest_timestamp is not None, "latest_timestamp should be set"
        assert isinstance(gen.latest_timestamp, float), "latest_timestamp should be a float"
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original
    print("  PASS: latest_brief updated after generate_brief call")


def test_system_state_summary_keys():
    """Verify summary has all expected keys."""
    gen = HandoverBriefGenerator()
    state = _healthy_state()
    summary = gen._build_summary(state)

    expected_keys = [
        "mode", "total_sensors", "healthy_sensors",
        "degraded_count", "anomaly_count", "mass_balance_flags",
    ]
    for key in expected_keys:
        assert key in summary, f"Missing key '{key}' in system_state_summary"

    assert summary["mode"] == "NORMAL"
    assert summary["total_sensors"] == 6
    assert summary["healthy_sensors"] == 6
    assert summary["degraded_count"] == 0
    assert summary["anomaly_count"] == 0
    assert summary["mass_balance_flags"] == 0
    print("  PASS: system_state_summary has all expected keys with correct values")


# ─── Runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_collect_system_state_structure,
        test_collect_state_counts_degraded_sensors,
        test_collect_state_limits_anomalies,
        test_fallback_brief_no_issues,
        test_fallback_brief_degraded_sensors,
        test_fallback_brief_mass_balance_flags,
        test_fallback_brief_with_anomalies,
        test_fallback_brief_with_stale_flags,
        test_fallback_brief_recommended_actions_critical,
        test_fallback_brief_recommended_actions_low,
        test_fallback_brief_source_is_fallback,
        test_build_user_message_format,
        test_generate_brief_uses_fallback_without_key,
        test_latest_brief_initially_none,
        test_latest_brief_updated_after_generate,
        test_system_state_summary_keys,
    ]

    print(f"\n{'='*60}")
    print("ConfidenceOS -- Module 6: Shift Handover Brief Generator Tests")
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
