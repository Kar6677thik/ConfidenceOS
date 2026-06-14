"""
test_integration_layer.py - Tests for read-only provider and asset model support.

Run from backend directory:
    python test_integration_layer.py
"""

import sys

from asset_model import (
    action_contract_decisions,
    criticality_weight,
    load_asset_model,
    mass_balance_validation,
    trusted_substitute_tags,
)
from tag_provider import CsvReplayProvider, OpcUaProvider, SimulatorProvider


def test_asset_model_loads_demo_vessel():
    model = load_asset_model()
    equipment = model["equipment"]
    relationship = mass_balance_validation(model)
    assert model["read_only_trust_layer"] is True
    assert equipment["equipment_id"] == "V-5100"
    assert relationship["validated_tag"] == "LT-5100"
    assert relationship["source_tags"] == ["FI-2010", "FO-2020"]
    assert "increase_feed" in action_contract_decisions(model)
    print("  PASS: Asset model describes demo vessel and mass-balance relationship")


def test_trusted_substitutes_use_asset_model():
    substitutes = trusted_substitute_tags(
        [
            {"sensor_id": "LT-5100", "sensor_type": "level"},
            {"sensor_id": "FI-2010", "sensor_type": "flow_in"},
            {"sensor_id": "FO-2020", "sensor_type": "flow_out"},
            {"sensor_id": "PT-3100", "sensor_type": "pressure"},
        ]
    )
    assert substitutes[:2] == ["FI-2010", "FO-2020"]
    assert "PT-3100" in substitutes
    assert criticality_weight("LT-5100", "level") == 3.0
    print("  PASS: Asset model contributes substitutes and criticality")


def test_simulator_provider_is_read_only():
    provider = SimulatorProvider()
    readings = provider.read_tags()
    assert provider.read_only is True
    assert provider.allows_control_writes is False
    assert len(readings) > 0
    try:
        provider.write_tag("LT-5100", 55)
    except PermissionError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("write_tag must not be allowed")
    print("  PASS: SimulatorProvider reads tags but rejects writes")


def test_placeholder_providers_are_read_only():
    csv_provider = CsvReplayProvider()
    opcua_provider = OpcUaProvider("opc.tcp://example.invalid:4840")
    assert csv_provider.read_tags() == []
    assert opcua_provider.read_tags() == []
    assert csv_provider.to_dict()["control_writes_enabled"] is False
    assert opcua_provider.to_dict()["writes_supported"] is False
    print("  PASS: CSV replay and OPC UA placeholders are read-only")


if __name__ == "__main__":
    tests = [
        test_asset_model_loads_demo_vessel,
        test_trusted_substitutes_use_asset_model,
        test_simulator_provider_is_read_only,
        test_placeholder_providers_are_read_only,
    ]

    print("\n" + "=" * 60)
    print("ConfidenceOS -- Integration Layer Tests")
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
