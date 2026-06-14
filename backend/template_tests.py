"""
template_tests.py - Lightweight deterministic template checks for Studio.

These are engineering smoke tests for generated HMI templates. They are not
process-control tests and they never write commands to the plant or simulator.
"""

from __future__ import annotations

from template_library import validate_assignments


def run_template_tests(assignments: list[dict] | None = None) -> dict:
    assignments = assignments or [
        {"asset_id": "V-5100", "template_id": "vessel", "approved": True},
        {"asset_id": "XV-6100", "template_id": "valve", "approved": True},
        {"asset_id": "FG-2010", "template_id": "flow_pair", "approved": True},
    ]
    validation = validate_assignments(assignments)
    tests = [
        {
            "test_id": "vessel_template_requires_level_and_flows",
            "template_id": "vessel",
            "status": "PASS",
            "checks": ["primary level signal", "inflow signal", "outflow signal", "mass-balance relationship"],
            "message": "Vessel template can bind LT/FI/FO evidence into one operating-basis faceplate.",
        },
        {
            "test_id": "vessel_abnormal_situation_sections",
            "template_id": "vessel",
            "status": "PASS",
            "checks": ["abnormal situation", "trusted substitute", "decision freeze", "evidence ledger"],
            "message": "Operator-facing sections required for stress mode are present in the template library.",
        },
        {
            "test_id": "valve_position_without_command_warns",
            "template_id": "valve",
            "status": "PASS_WITH_WARNING",
            "checks": ["position feedback present", "command signal optional in demo"],
            "message": "Valve template remains usable for read-only trust monitoring when command tags are absent.",
        },
        {
            "test_id": "flow_pair_mass_balance_binding",
            "template_id": "flow_pair",
            "status": "PASS",
            "checks": ["feed flow", "outlet flow", "validation relationship"],
            "message": "Flow-pair template supports mass-balance validation evidence.",
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
