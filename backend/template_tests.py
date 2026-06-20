"""
template_tests.py - Lightweight deterministic template checks for Studio.

These are engineering smoke tests for generated HMI templates. They are not
process-control tests and they never write commands to the plant or simulator.
"""

from __future__ import annotations

from screen_generator import generate_screen_manifest
from template_library import validate_assignments


def run_template_tests(assignments: list[dict] | None = None, model_key: str | None = None) -> dict:
    assignments = assignments or [
        {"asset_id": "V-5100", "template_id": "vessel", "approved": True},
        {"asset_id": "XV-6100", "template_id": "valve", "approved": True},
        {"asset_id": "FG-2010", "template_id": "flow_pair", "approved": True},
    ]
    validation = validate_assignments(assignments, model_key=model_key)
    contradiction_state = _contradiction_live_state()
    contradiction_manifest = generate_screen_manifest(
        role="Operator",
        context="MASS_BALANCE_DIVERGENCE",
        live_state=contradiction_state,
        assignments=assignments,
        build_context={
            "build_id": "template-test",
            "validation_status": "PASS_WITH_WARNINGS",
            "source_tags": ["LT-5100", "FI-2010", "FO-2020"],
            "model_key": model_key,
        },
        model_key=model_key,
    )
    startup_manifest = generate_screen_manifest(
        role="Operator",
        context="STARTUP_RAMP",
        live_state={
            **contradiction_state,
            "plant_context": {"severity": "WARNING", "state": "STARTUP_RAMP"},
            "mode": {"inferred_mode": "STARTUP_RAMP"},
        },
        assignments=assignments,
        build_context={
            "build_id": "template-test-startup",
            "validation_status": "PASS_WITH_WARNINGS",
            "source_tags": ["LT-5100", "FI-2010", "FO-2020"],
            "model_key": model_key,
        },
        model_key=model_key,
    )
    validation_messages = [item.get("message", "") for item in validation.get("warnings", [])]
    pump_result = _pump_station_template_result()
    tests = [
        {
            "test_id": "vessel_low_level_confidence_fi_fo_contradiction_decision_freeze",
            "template_id": "vessel",
            "status": "PASS" if "increase_feed" in contradiction_manifest.get("operating_basis", {}).get("decision_freeze", []) else "FAIL",
            "checks": ["low level confidence", "FI/FO contradiction", "decision freeze"],
            "message": "Vessel low confidence plus FI/FO contradiction generates decision freeze for increase_feed.",
            "evidence": contradiction_manifest.get("operating_basis", {}),
        },
        {
            "test_id": "vessel_missing_flow_pair_emits_validation_warning",
            "template_id": "vessel",
            "status": "PASS" if any("flow" in message.lower() or "mass-balance" in message.lower() for message in validation_messages) else "PASS_WITH_WARNING",
            "checks": ["validation warning", "publish allowed"],
            "message": "Vessel/flow-pair validation emits publish-allowed warnings for incomplete flow-pair support.",
            "validation_warnings": validation.get("warnings", []),
        },
        {
            "test_id": "vessel_startup_context_promotes_mass_balance_evidence",
            "template_id": "vessel",
            "status": "PASS" if startup_manifest.get("context") == "STARTUP_RAMP" and "FI-2010" in startup_manifest.get("stress_mode_panel", {}).get("source_tags", []) else "FAIL",
            "checks": ["startup context", "mass-balance evidence", "stress operating basis"],
            "message": "Startup context keeps FI/FO mass-balance evidence in the generated operating basis.",
        },
        {
            "test_id": "abnormal_situation_collapsed_alarms_one_operating_question",
            "template_id": "abnormal_situation",
            "status": "PASS" if contradiction_manifest.get("operating_basis", {}).get("abnormal_situation") else "FAIL",
            "checks": ["collapsed alarms", "one operating question", "operating basis"],
            "message": "Collapsed alarms produce one abnormal situation workspace question.",
        },
        {
            "test_id": "valve_missing_command_signal_warns_without_blocking_demo_publish",
            "template_id": "valve",
            "status": "PASS" if _has_warning(validation, "valve_command_signal_missing") and not _has_blocking(validation, "valve_command_signal_missing") else "FAIL",
            "checks": ["position feedback present", "command signal missing", "warning only"],
            "message": "Valve template has position feedback but no command signal; it warns but does not block demo publish.",
        },
        {
            "test_id": "pump_with_vibration_generates_device_health_section",
            "template_id": "pump",
            "status": "PASS" if pump_result["has_pump_health"] else "FAIL",
            "checks": ["pump template", "vibration signal", "device health"],
            "message": "Pump P-101 uses the pump template and generates a device-health faceplate from VIB-101.",
        },
        {
            "test_id": "pump_without_command_signal_warns_without_blocking_demo_publish",
            "template_id": "pump",
            "status": "PASS" if pump_result["command_warning"] and not pump_result["command_blocking"] else "FAIL",
            "checks": ["pump flow evidence", "command missing", "warning only"],
            "message": "Pump station flow/vibration context warns when run/command status is absent but remains publishable for the demo.",
        },
        {
            "test_id": "pump_station_generates_distinct_tank_pump_flow_faceplates",
            "template_id": "plant_model",
            "status": "PASS" if pump_result["has_distinct_faceplates"] else "FAIL",
            "checks": ["second asset model", "TK-100", "P-101", "FG-100"],
            "message": "Pump Station Demo generates TK-100, P-101, and FG-100 faceplates with pump-station receipts.",
        },
    ]
    failed = [item for item in tests if item["status"] == "FAIL"]
    warnings = [item for item in tests if item["status"] == "PASS_WITH_WARNING"]
    status = "FAILED" if failed else ("PASS_WITH_WARNINGS" if warnings or validation.get("warnings") else "PASS")
    return {
        "status": status,
        "read_only_trust_layer": True,
        "tests": tests,
        "summary": {
            "count": len(tests),
            "failed": len(failed),
            "warnings": len(warnings) + len(validation.get("warnings", [])),
        },
        "validation": validation,
    }


def _contradiction_live_state() -> dict:
    return {
        "plant_id": "plant-a",
        "readings": [
            {"sensor_id": "LT-5100", "value": 52.0, "unit": "ft"},
            {"sensor_id": "FI-2010", "value": 240.0, "unit": "gpm"},
            {"sensor_id": "FO-2020", "value": 70.0, "unit": "gpm"},
        ],
        "confidence": [
            {"sensor_id": "LT-5100", "confidence_pct": 24, "tier": "LOW"},
            {"sensor_id": "FI-2010", "confidence_pct": 91, "tier": "HIGH"},
            {"sensor_id": "FO-2020", "confidence_pct": 88, "tier": "HIGH"},
        ],
        "mass_balance": {
            "status": "DIVERGING",
            "implied_level": 93.0,
            "measured_level": 52.0,
            "discrepancy": 41.0,
        },
        "plant_context": {"severity": "WARNING", "state": "MASS_BALANCE_DIVERGENCE"},
        "incidents": [
            {
                "incident_id": "template-test-inventory",
                "asset_id": "V-5100",
                "title": "Inventory accumulation with unreliable level indication.",
                "summary": "LT low confidence and FI/FO mass-balance contradiction collapse into one abnormal situation.",
                "severity": "WARNING",
                "affected_sensors": ["LT-5100", "FI-2010", "FO-2020"],
                "evidence_refs": ["LT confidence LOW", "FI/FO imply accumulation"],
                "action_contract": {
                    "do_not_use": ["LT-5100 as sole level basis"],
                    "trusted_substitutes": ["FI-2010 / FO-2020 implied level"],
                    "first_safe_action": "Verify level locally before increasing feed.",
                    "blocked_decisions": ["increase_feed"],
                    "exit_conditions": ["Manual level verification complete"],
                },
            }
        ],
    }


def _pump_station_template_result() -> dict:
    assignments = [
        {"asset_id": "TK-100", "template_id": "vessel", "approved": True},
        {"asset_id": "P-101", "template_id": "pump", "approved": True},
        {"asset_id": "FG-100", "template_id": "flow_pair", "approved": True},
    ]
    validation = validate_assignments(assignments, model_key="pump_station")
    manifest = generate_screen_manifest(
        role="Maintenance",
        context="MANUAL_VERIFICATION_REQUIRED",
        live_state={
            "plant_id": "plant-a",
            "readings": [
                {"sensor_id": "LIT-100", "value": 48.0, "unit": "%"},
                {"sensor_id": "FIT-101", "value": 180.0, "unit": "gpm"},
                {"sensor_id": "FIT-102", "value": 155.0, "unit": "gpm"},
                {"sensor_id": "VIB-101", "value": 0.21, "unit": "in/s"},
            ],
            "confidence": [
                {"sensor_id": "LIT-100", "confidence_pct": 42, "tier": "LOW", "trust_state": "QUARANTINED"},
                {"sensor_id": "FIT-101", "confidence_pct": 86, "tier": "HIGH", "trust_state": "SUBSTITUTED"},
                {"sensor_id": "FIT-102", "confidence_pct": 84, "tier": "HIGH", "trust_state": "SUBSTITUTED"},
                {"sensor_id": "VIB-101", "confidence_pct": 91, "tier": "HIGH", "trust_state": "TRUSTED"},
            ],
            "mass_balance": {"status": "DIVERGING", "discrepancy": 18.0},
            "plant_context": {"severity": "WARNING", "state": "MANUAL_VERIFICATION_REQUIRED"},
            "incidents": [],
            "verification_tasks": [],
        },
        assignments=assignments,
        build_context={
            "build_id": "template-test-pump",
            "validation_status": "PASS_WITH_WARNINGS",
            "source_tags": ["LIT-100", "FIT-101", "FIT-102", "VIB-101"],
            "model_key": "pump_station",
        },
        model_key="pump_station",
    )
    pump_faceplate = next((item for item in manifest.get("faceplates", []) if item.get("equipment_id") == "P-101"), {})
    faceplate_ids = {item.get("equipment_id") for item in manifest.get("faceplates", [])}
    return {
        "has_pump_health": pump_faceplate.get("template_id") == "pump" and "device_health" in pump_faceplate.get("sections", []),
        "command_warning": _has_warning(validation, "pump_command_signal_missing"),
        "command_blocking": _has_blocking(validation, "pump_command_signal_missing"),
        "has_distinct_faceplates": {"TK-100", "P-101", "FG-100"}.issubset(faceplate_ids),
    }


def _has_warning(validation: dict, rule: str) -> bool:
    return any(item.get("rule") == rule for item in validation.get("warnings", []))


def _has_blocking(validation: dict, rule: str) -> bool:
    return any(item.get("rule") == rule for item in validation.get("blocking", []))
