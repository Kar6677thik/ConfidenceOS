"""
Focused checks for the read-only HMI Compiler pipeline.
"""

from __future__ import annotations

import unittest

from hmi_compiler import mapping_court_for_tag, run_build
from studio_service import DEFAULT_ASSIGNMENTS
from template_tests import run_template_tests


class HmiCompilerTests(unittest.TestCase):
    def test_default_build_blocks_bad_tag(self):
        build = run_build({"assignments": DEFAULT_ASSIGNMENTS}, build_id="hmi-build-test")
        self.assertEqual(build["status"], "FAILED")
        self.assertFalse(build["can_publish"])
        blocking_tags = {
            item.get("raw_tag")
            for item in build["validation"]["blocking"]
        }
        self.assertIn("BAD_TAG_123", blocking_tags)
        self.assertEqual(build["generated_manifest"], {})

    def test_spare_tag_is_info_receipt(self):
        build = run_build({"assignments": DEFAULT_ASSIGNMENTS}, build_id="hmi-build-test")
        info_messages = [
            receipt.get("message", "")
            for receipt in build["receipts"]
            if receipt.get("severity") == "INFO"
        ]
        self.assertTrue(any("UNUSED_SPARE_AI_09" in message for message in info_messages))

    def test_mapping_court_has_traceable_fields(self):
        row = mapping_court_for_tag("U15_LT_5100.PV")
        for key in ("evidence", "counter_evidence", "verdict", "approval_required", "suggestion_type"):
            self.assertIn(key, row)
        self.assertEqual(row["suggestion_label"], "deterministic rule active")
        self.assertEqual(row["ai_suggestion"], "AI suggestion optional")
        self.assertEqual(row["approval_label"], "engineer approval required")

    def test_build_can_pass_when_bad_tag_is_ignored_with_reason(self):
        build = run_build(
            {
                "assignments": DEFAULT_ASSIGNMENTS,
                "approved_bindings": _approved_dirty_bindings(),
                "ignored_raw_tags": {
                    "BAD_TAG_123": "Confirmed spare import artifact during Studio validation.",
                },
            },
            build_id="hmi-build-test",
        )
        self.assertNotEqual(build["status"], "FAILED")
        self.assertTrue(build["can_publish"])
        self.assertIn("faceplates", build["generated_manifest"])

    def test_dirty_critical_mapping_requires_approval(self):
        build = run_build(
            {
                "assignments": DEFAULT_ASSIGNMENTS,
                "ignored_raw_tags": {
                    "BAD_TAG_123": "Confirmed spare import artifact during Studio validation.",
                },
            },
            build_id="hmi-build-test",
        )
        rules = {item.get("rule") for item in build["validation"]["blocking"]}
        self.assertIn("dirty_critical_mapping_requires_engineer_approval", rules)

    def test_generated_items_include_receipts(self):
        build = run_build(
            {
                "assignments": DEFAULT_ASSIGNMENTS,
                "approved_bindings": _approved_dirty_bindings(),
                "ignored_raw_tags": {
                    "BAD_TAG_123": "Confirmed spare import artifact during Studio validation.",
                },
            },
            build_id="hmi-build-test",
        )
        manifest = build["generated_manifest"]
        for collection in ("screens", "faceplates", "role_sections"):
            for item in manifest[collection]:
                for key in ("generated_id", "build_id", "asset_id", "template_id", "template_version", "source_tags", "role_policy", "context_policy", "validation_status", "receipt"):
                    self.assertIn(key, item)
                self.assertIn("generated_because", item["receipt"])
                self.assertIn("source_files", item["receipt"])
        self.assertIn("receipt", manifest["stress_mode_panel"])

    def test_template_tests_return_results(self):
        result = run_template_tests(DEFAULT_ASSIGNMENTS)
        self.assertIn(result["status"], {"PASS", "PASS_WITH_WARNINGS"})
        self.assertGreaterEqual(result["summary"]["count"], 3)


def _approved_dirty_bindings():
    return [
        {"raw_tag": "U15_LT_5100.PV"},
        {"raw_tag": "15-FI-2010"},
        {"raw_tag": "FO2020_RATE"},
        {"raw_tag": "ZT6100.POS"},
        {"raw_tag": "PT_3100_PROCESS"},
        {"raw_tag": "TEMP4100"},
    ]


if __name__ == "__main__":
    unittest.main()
