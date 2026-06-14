"""
plants.py — Multi-plant manager for ConfidenceOS V2.

Holds 3 independent plant instances, each with its own simulator,
confidence engine, mass-balance engine, startup manager, and handover generator.

Plants:
  plant-a: Raffinate Splitter Unit (Texas City scenario)
  plant-b: North Sea Gas Compression (cold restart)
  plant-c: Municipal Water Treatment (valve decoupling)
"""

from pathlib import Path
from simulator import SensorSimulator
from tag_provider import SimulatorProvider
from confidence import ConfidenceEngine
from mass_balance import MassBalanceEngine, DEFAULT_TOLERANCE
from startup import StartupManager
from handover import HandoverBriefGenerator
from mode_inference import ModeInferenceEngine


# ── Plant configurations ────────────────────────────────────────────────────

PLANT_CONFIGS = {
    "plant-a": {
        "name": "Raffinate Splitter Unit",
        "type": "Refinery",
        "location": "Texas City, TX",
        "scenario": "scenario.json",
        "calibration_ages": {
            "LT-5100": 47.0,  # Texas City — 47 days uncalibrated
            "FI-2010": 12.0,
            "FO-2020": 15.0,
            "PT-3100": 5.0,
            "TT-4100": 30.0,
            "ZT-6100": 8.0,
        },
    },
    "plant-b": {
        "name": "North Sea Gas Compression",
        "type": "Gas Processing",
        "location": "Aberdeen, UK",
        "scenario": "scenario_b.json",
        "calibration_ages": {
            "LT-5100": 10.0,
            "FI-2010": 20.0,
            "FO-2020": 18.0,
            "PT-3100": 35.0,
            "TT-4100": 55.0,  # Temperature sensor overdue
            "ZT-6100": 5.0,
        },
    },
    "plant-c": {
        "name": "Municipal Water Treatment",
        "type": "Water Treatment",
        "location": "Melbourne, AU",
        "scenario": "scenario_c.json",
        "calibration_ages": {
            "LT-5100": 8.0,
            "FI-2010": 6.0,
            "FO-2020": 7.0,
            "PT-3100": 3.0,
            "TT-4100": 10.0,
            "ZT-6100": 40.0,  # Valve sensor — somewhat aged
        },
    },
}


class PlantInstance:
    """A single plant with all its engines."""

    def __init__(self, plant_id: str, config: dict):
        self.plant_id = plant_id
        self.config = config
        self.name = config["name"]
        self.plant_type = config["type"]
        self.location = config["location"]

        # Create independent instances
        self.simulator = SensorSimulator()
        self.tag_provider = SimulatorProvider(self.simulator)
        self.confidence_engine = ConfidenceEngine()
        self.mass_balance_engine = MassBalanceEngine()
        self.startup_manager = StartupManager()
        self.mode_inference_engine = ModeInferenceEngine()
        self.handover_generator = HandoverBriefGenerator()

        # Load scenario
        scenario_path = Path(__file__).parent / config["scenario"]
        if scenario_path.exists():
            self.simulator.load_scenario(scenario_path)

        # Set calibration ages
        for sensor_id, age in config["calibration_ages"].items():
            self.confidence_engine.set_calibration_age(sensor_id, age)

        # Latest state caches
        self.latest_confidence: dict[str, dict] = {}
        self.latest_mb_state: dict = {}
        self.latest_readings: list = []
        self.latest_mode_payload: dict = {}
        self.latest_context: dict = {}
        self.latest_inferred_mode: dict = {}
        self.latest_incidents: list = []
        self.latest_incident_timeline: list = []
        self.latest_new_anomalies: list = []
        self.verification_tokens: list = []
        self.confidence_debt_state: dict = {}
        self.latest_confidence_debt: list = []
        self.latest_handover_debt: dict = {}

    def info(self) -> dict:
        """Return plant metadata."""
        return {
            "plant_id": self.plant_id,
            "name": self.name,
            "type": self.plant_type,
            "location": self.location,
            "tag_provider": self.tag_provider.to_dict(),
        }


class PlantManager:
    """Manages all plant instances."""

    def __init__(self):
        self.plants: dict[str, PlantInstance] = {}
        for plant_id, config in PLANT_CONFIGS.items():
            self.plants[plant_id] = PlantInstance(plant_id, config)

    def get(self, plant_id: str) -> PlantInstance:
        """Get a plant instance by ID. Returns plant-a as default."""
        return self.plants.get(plant_id, self.plants["plant-a"])

    def get_all(self) -> dict[str, PlantInstance]:
        """Get all plant instances."""
        return self.plants

    def compute_fleet_risk_score(self, plant: PlantInstance) -> float:
        """
        Compute Plant Risk Score per PRD §4.3:
        
        risk = (1 - avg_confidence) * 0.40
             + active_critical_flags * 0.25
             + mass_balance_discrepancy_norm * 0.20
             + max_calibration_age_norm * 0.15
        """
        # Average confidence
        conf_values = [c.get("confidence_pct", 100) for c in plant.latest_confidence.values()]
        avg_conf = sum(conf_values) / len(conf_values) / 100.0 if conf_values else 1.0

        # Active critical flags
        flags = plant.latest_mb_state.get("flags", [])
        critical_count = sum(1 for f in flags if f.get("severity") == "CRITICAL")
        warning_count = sum(1 for f in flags if f.get("severity") == "WARNING")
        flag_score = min(1.0, (critical_count * 0.5 + warning_count * 0.2))

        # Mass-balance discrepancy (normalize: 0 = no gap, 1 = gap > 10 units)
        discrepancy = abs(plant.latest_mb_state.get("discrepancy", 0))
        mb_score = min(1.0, discrepancy / 10.0)

        # Max calibration age (normalize: 0 = fresh, 1 = 90+ days)
        max_cal_age = max(plant.config["calibration_ages"].values())
        cal_score = min(1.0, max_cal_age / 90.0)

        risk = (
            (1.0 - avg_conf) * 0.40
            + flag_score * 0.25
            + mb_score * 0.20
            + cal_score * 0.15
        )
        return round(risk * 100, 1)

    def get_fleet_summary(self) -> list[dict]:
        """Get fleet-level summary for all plants."""
        summaries = []
        for plant_id, plant in self.plants.items():
            conf_values = [c.get("confidence_pct", 100) for c in plant.latest_confidence.values()]
            avg_conf = round(sum(conf_values) / len(conf_values), 1) if conf_values else 100.0

            risk_score = self.compute_fleet_risk_score(plant)
            
            # Count flags by type
            flags = plant.latest_mb_state.get("flags", [])
            low_conf_sensors = [
                sid for sid, c in plant.latest_confidence.items()
                if c.get("tier") in ("LOW", "CRITICAL")
            ]

            # Determine status
            if risk_score >= 60:
                status = "CRITICAL"
            elif risk_score >= 35:
                status = "WARNING"
            elif plant.startup_manager.is_active:
                status = "STARTUP"
            else:
                status = "NORMAL"

            summaries.append({
                "plant_id": plant_id,
                "name": plant.name,
                "type": plant.plant_type,
                "location": plant.location,
                "health_pct": avg_conf,
                "risk_score": risk_score,
                "status": status,
                "active_flags": len(flags) + len(low_conf_sensors),
                "startup_active": plant.startup_manager.is_active,
                "top_issues": _get_top_issues(plant),
                "sensors": plant.latest_confidence,
            })

        # Sort by risk score descending (highest risk first)
        summaries.sort(key=lambda s: s["risk_score"], reverse=True)

        # Assign risk ranking
        for i, s in enumerate(summaries):
            s["risk_rank"] = i + 1

        return summaries


def _get_top_issues(plant: PlantInstance) -> list[str]:
    """Get top 3 issues for a plant card display."""
    issues = []

    # Mass-balance flags
    for f in plant.latest_mb_state.get("flags", []):
        issues.append(f.get("message", "Mass-balance flag"))

    # Low/critical confidence sensors
    for sid, c in plant.latest_confidence.items():
        tier = c.get("tier", "HIGH")
        if tier in ("LOW", "CRITICAL"):
            pct = c.get("confidence_pct", 0)
            issues.append(f"{sid}: {pct:.0f}% {tier}")
        elif tier == "MEDIUM":
            pct = c.get("confidence_pct", 0)
            issues.append(f"{sid}: {pct:.0f}% {tier}")

    return issues[:3]
