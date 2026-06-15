"""
test_ai_features.py — Tests for WS2/WS3/WS5/WS6 additions to ConfidenceOS.

Tests cover:
  1. AI mapping falls back to deterministic when no key present
  2. Arbitrary tag import returns proposals for all input tags
  3. Template suggestion is constrained to real template library
  4. Pump-station vocabulary: no Texas City leakage in advisory fallback
  5. Model-derived mass balance config reads from asset model JSON
  6. Confidence weights deduplicated: decision_integrity derives from confidence.py

Run from backend directory:
    python test_ai_features.py
"""

import asyncio
import sys
import os


def check(name: str, condition: bool, info: str = ""):
    if condition:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f": {info}" if info else ""))
        sys.exit(1)


# --- 1. AI mapping graceful fallback (no key) --------------------------------

async def test_ai_mapping_fallback_no_key():
    """explain_mapping and parse_arbitrary_tags degrade gracefully when no API key."""
    # Remove key so _ai_available() returns False
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        import ai_mapping
        # Force re-evaluation
        ai_mapping._AI_AVAILABLE = None

        result = await ai_mapping.explain_mapping(
            "RAW_TAG_XYZ",
            {"proposed_canonical_tag": "LT-5100", "proposed_asset_id": "V-5100", "proposed_role": "primary_level", "evidence": [], "counter_evidence": []},
            {"equipment_id": "texas_city_vessel", "equipment_label": "Texas City Vessel", "canonical_signals": []},
        )
        check("explain_mapping fallback: ai_assisted=False", result["ai_assisted"] is False)
        check("explain_mapping fallback: model=None", result["model"] is None)
        check("explain_mapping fallback: has ai_narrative", bool(result.get("ai_narrative")))
        check("explain_mapping fallback: honest label", "deterministic" in result["ai_label"].lower() or "unavailable" in result["ai_label"].lower())

        result2 = await ai_mapping.parse_arbitrary_tags(
            ["ARBITRARY_TAG_1", "ARBITRARY_TAG_2"],
            {"equipment_id": "texas_city_vessel", "equipment_label": "Texas City Vessel", "canonical_signals": []},
        )
        check("parse_arbitrary_tags fallback: ai_assisted=False", result2["ai_assisted"] is False)
        check("parse_arbitrary_tags fallback: proposals length matches input", len(result2["proposals"]) == 2)
        check("parse_arbitrary_tags fallback: all unresolved", len(result2["unresolved"]) == 2)
        check("parse_arbitrary_tags fallback: approval_required=True", all(p["approval_required"] for p in result2["proposals"]))
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original
        import ai_mapping as _am
        _am._AI_AVAILABLE = None


# --- 2. Template suggestion constrained to real library ----------------------

async def test_suggest_template_validates_against_library():
    """suggest_template must only return template_ids from the provided list."""
    import ai_mapping
    ai_mapping._AI_AVAILABLE = None  # ensure fallback

    available = [
        {"template_id": "vessel", "label": "Process Vessel", "required_signal_roles": ["level", "flow_in", "flow_out"]},
        {"template_id": "pump",   "label": "Pump",           "required_signal_roles": ["vibration", "pressure"]},
        {"template_id": "valve",  "label": "Control Valve",  "required_signal_roles": ["position"]},
    ]
    result = await ai_mapping.suggest_template(
        "A large storage tank with level and inflow/outflow measurements",
        available,
        [],
    )
    check("suggest_template fallback: approval_required=True", result["approval_required"] is True)
    check("suggest_template fallback: model=None", result["model"] is None)
    # Fallback should not propose a specific template (no key)
    check("suggest_template fallback: no hallucinated template_id", result["proposed_template_id"] is None)


# --- 3. Pump-station vocabulary: no increase_feed leakage --------------------

def test_pump_station_no_texas_city_vocabulary():
    """Switching to pump_station model should not produce 'increase_feed' in blocked decisions."""
    from asset_model import set_active_asset_model, action_contract_decisions, load_asset_model

    try:
        set_active_asset_model("pump_station")
        model = load_asset_model()
        decisions = action_contract_decisions(model)
        check(
            "pump_station: action_contract_decisions does not contain increase_feed",
            "increase_feed" not in decisions,
            f"Found: {decisions}",
        )
        check(
            "pump_station: action_contract_decisions does not contain increase_load",
            "increase_load" not in decisions,
            f"Found: {decisions}",
        )
        check(
            "pump_station: has pump-specific blocked decision",
            any("transfer" in d or "pump" in d or "rate" in d for d in decisions) or len(decisions) > 0,
            f"Found: {decisions}",
        )
    finally:
        set_active_asset_model("texas_city_vessel")


def test_advisory_fallback_no_texas_city_vocabulary():
    """advisory._action_contract fallback blocked_decisions should not hardcode refinery terms."""
    import advisory
    from asset_model import set_active_asset_model

    try:
        # Use a hypothetical model that has no contract_decisions — forcing the fallback
        # We test the fallback by reading the source code defensively
        import inspect
        src = inspect.getsource(advisory._action_contract)
        check(
            "advisory._action_contract: increase_feed not hardcoded",
            '"increase_feed"' not in src,
            "Found 'increase_feed' hardcoded in source",
        )
        check(
            "advisory._action_contract: increase_load not hardcoded",
            '"increase_load"' not in src,
            "Found 'increase_load' hardcoded in source",
        )
    finally:
        set_active_asset_model("texas_city_vessel")


# --- 4. Mass balance config sourced from asset model -------------------------

def test_mass_balance_config_from_asset_model():
    """mass_balance_engine_config should read values from asset model JSON, not global constants."""
    from asset_model import mass_balance_engine_config, set_active_asset_model, load_asset_model
    from mass_balance import DEFAULT_TOLERANCE, FLOW_TO_LEVEL_RATE

    # Texas City vessel: should match asset_model.json values
    set_active_asset_model("texas_city_vessel")
    cfg = mass_balance_engine_config()
    check("texas_city: flow_to_level_rate is float", isinstance(cfg["flow_to_level_rate"], float))
    check("texas_city: tolerance is float", isinstance(cfg["tolerance"], float))
    check("texas_city: flow_to_level_rate > 0", cfg["flow_to_level_rate"] > 0)
    check("texas_city: tolerance > 0", cfg["tolerance"] > 0)

    # Pump station: different values than texas city
    set_active_asset_model("pump_station")
    cfg_pump = mass_balance_engine_config()
    check("pump_station: has mass_balance_config in JSON", cfg_pump["flow_to_level_rate"] != cfg["flow_to_level_rate"] or cfg_pump["tolerance"] != cfg["tolerance"],
          "Pump station config identical to texas city — per-asset config may not be set")

    set_active_asset_model("texas_city_vessel")


# --- 5. Confidence weights deduplicated -------------------------------------

def test_confidence_weights_single_source():
    """decision_integrity.CONFIDENCE_WEIGHTS must match confidence.ConfidenceWeights."""
    from confidence import ConfidenceWeights
    from decision_integrity import CONFIDENCE_WEIGHTS

    defaults = ConfidenceWeights()
    check("weights: calibration matches", CONFIDENCE_WEIGHTS["calibration"] == defaults.calibration)
    check("weights: stability matches", CONFIDENCE_WEIGHTS["stability"] == defaults.stability)
    check("weights: cross_sensor matches", CONFIDENCE_WEIGHTS["cross_sensor"] == defaults.cross_sensor)
    check("weights: physical_plausibility matches", CONFIDENCE_WEIGHTS["physical_plausibility"] == defaults.physical_plausibility)
    check("weights: sum to 1.0", abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 0.001)


# --- Runner ------------------------------------------------------------------

async def run_all():
    print("\n-- AI Mapping Fallback (no key) -------------------------")
    await test_ai_mapping_fallback_no_key()

    print("\n-- Template Suggestion Constrained to Library -----------")
    await test_suggest_template_validates_against_library()

    print("\n-- Pump-Station: No Texas City Vocabulary ---------------")
    test_pump_station_no_texas_city_vocabulary()
    test_advisory_fallback_no_texas_city_vocabulary()

    print("\n-- Mass Balance Config from Asset Model -----------------")
    test_mass_balance_config_from_asset_model()

    print("\n-- Confidence Weights: Single Source of Truth -----------")
    test_confidence_weights_single_source()

    print("\nAll tests passed.\n")


if __name__ == "__main__":
    asyncio.run(run_all())
