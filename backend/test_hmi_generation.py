"""
Focused tests for the metadata-driven Runtime/Studio layer.

Run:
    python -m unittest test_hmi_generation.py
"""

import unittest

from model_graph import get_assets, get_model_graph, get_navigation, get_signals
from screen_generator import generate_screen_manifest
from shift_channel import build_shift_channel, reset_notes
from studio_service import auto_map, publish, reset, validation
from template_library import validate_assignments


class DemoPlant:
    latest_handover_debt = {
        "entries": [
            {
                "id": "freeze:feed-increase",
                "type": "active_decision_freeze",
                "title": "Feed increase decision frozen",
                "severity": "WARNING",
                "required_action": "Use trusted substitute before changing feed.",
            }
        ]
    }
    latest_incidents = [
        {
            "incident_id": "inc-1",
            "title": "Inventory accumulation with unreliable level indication.",
            "severity": "WARNING",
            "summary": "Alarm collapse produced one abnormal situation.",
            "handover_required": True,
            "action_contract": {"do_not_use": ["LT-5100"]},
        }
    ]
    verification_tokens = [
        {
            "sensor_id": "LT-5100",
            "verification_type": "field_round",
            "valid_until": "2026-06-14T12:00:00Z",
        }
    ]
    latest_incident_timeline = [
        {
            "event_id": "event-1",
            "event_type": "mode_detected",
            "timestamp": 1,
            "message": "Startup ramp detected.",
            "severity": "INFO",
        }
    ]
    latest_confidence_debt = [
        {
            "sensor_id": "LT-5100",
            "priority_language": "High confidence debt; schedule verification.",
        }
    ]


class HmiGenerationTests(unittest.TestCase):
    def tearDown(self):
        reset()
        reset_notes()

    def test_model_graph_loads_hierarchy_and_signals(self):
        graph = get_model_graph()
        self.assertTrue(graph["read_only_trust_layer"])
        self.assertGreaterEqual(len(graph["nodes"]), 6)
        self.assertTrue(any(edge["type"] == "validates" for edge in graph["edges"]))

        assets = get_assets()
        signals = get_signals()
        navigation = get_navigation()
        self.assertTrue(any(asset["asset_id"] == "V-5100" for asset in assets))
        self.assertTrue(any(signal["id"] == "LT-5100" for signal in signals))
        self.assertTrue(navigation["areas"])

    def test_template_validation_catches_missing_required_signals(self):
        valid = validate_assignments([{"asset_id": "V-5100", "template_id": "vessel"}])
        self.assertEqual(valid["items"][0]["status"], "valid")

        invalid = validate_assignments([{"asset_id": "XV-6100", "template_id": "vessel"}])
        self.assertEqual(invalid["status"], "warnings")
        self.assertTrue(invalid["warnings"])

    def test_generated_screens_are_role_aware_and_read_only(self):
        for role in ["Operator", "Maintenance", "Engineer", "Manager", "Auditor"]:
            manifest = generate_screen_manifest(role=role, context="auto")
            self.assertEqual(manifest["route"], "/runtime")
            self.assertTrue(manifest["read_only_trust_layer"])
            self.assertIn("provenance", manifest)
            self.assertGreaterEqual(len(manifest["faceplates"]), 1)

    def test_studio_automap_requires_publish_before_runtime(self):
        reset()
        suggestions = auto_map()
        self.assertGreaterEqual(len(suggestions["suggestions"]), 1)

        validation_before = validation()
        self.assertIn("status", validation_before)

        published = publish()
        self.assertEqual(published["status"], "published")
        self.assertTrue(published["read_only_trust_layer"])

    def test_shift_channel_combines_operational_debt(self):
        reset_notes()
        channel = build_shift_channel("plant-a", DemoPlant())
        self.assertTrue(channel["pinned"])
        self.assertTrue(channel["thread"])
        self.assertIn("handover", channel["summary"])


if __name__ == "__main__":
    unittest.main()
