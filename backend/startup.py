"""
startup.py — Startup Mode Manager for ConfidenceOS (Module 5).

Plant startups are the highest-risk operational period. The Texas City explosion
and Esso Longford disaster both occurred during startup/restart.

Startup Mode activates heightened scrutiny:
  - Confidence tier threshold for MEDIUM raised from 50% to 70%
    (more sensors flagged as LOW)
  - Mass-balance tolerance tightened by 50%
  - Stale reading detection: flag readings unchanged for > 8 minutes,
    requiring manual acknowledgement

PRD Reference: §4.5
"""

import time
from dataclasses import dataclass, field
from typing import Optional


# ─── Data types ──────────────────────────────────────────────────────────────

@dataclass
class StaleReadingFlag:
    """Flag for a sensor with an unchanged reading in startup mode."""
    sensor_id: str
    duration_seconds: float
    last_value: float
    acknowledged: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "duration_seconds": round(self.duration_seconds, 1),
            "last_value": round(self.last_value, 2),
            "acknowledged": self.acknowledged,
            "timestamp": self.timestamp,
        }


# ─── Startup Mode Manager ───────────────────────────────────────────────────

class StartupManager:
    """
    Manages startup mode state and heightened scrutiny behaviors.

    When active:
      - Confidence tier thresholds shift: MEDIUM boundary raised 50% → 70%
      - Mass-balance tolerance tightened by 50%
      - Stale reading detection: flag readings unchanged > 8 min

    Usage:
        manager = StartupManager()
        manager.activate()
        stale = manager.check_stale_readings(readings, now)
    """

    # Stale reading threshold in seconds (8 minutes per PRD §4.5)
    STALE_THRESHOLD_SECONDS = 480.0

    # Normal tier boundaries (matches confidence.py _tier_from_pct)
    NORMAL_TIERS = {"HIGH": 80, "MEDIUM": 50, "LOW": 20, "CRITICAL": 0}

    # Startup tier boundaries — MEDIUM raised from 50 to 70 per PRD §4.5
    STARTUP_TIERS = {"HIGH": 80, "MEDIUM": 70, "LOW": 20, "CRITICAL": 0}

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.is_active: bool = False
        self._activated_at: Optional[float] = None
        self._stale_threshold_seconds = float(config.get("stale_threshold_seconds", self.STALE_THRESHOLD_SECONDS))
        self._normal_tiers = dict(config.get("normal_tiers") or self.NORMAL_TIERS)
        self._startup_tiers = dict(config.get("startup_tiers") or self.STARTUP_TIERS)
        self._mass_balance_tolerance_multiplier = float(
            config.get("mass_balance_tolerance_multiplier", 0.5)
        )

        # Track last change time and value per sensor for stale detection
        self._last_change: dict[str, tuple[float, float]] = {}
        # sensor_id → (timestamp_of_last_change, value_at_last_change)

        self._stale_flags: dict[str, StaleReadingFlag] = {}

    def activate(self) -> None:
        """Activate startup mode — heightened scrutiny enabled."""
        self.is_active = True
        self._activated_at = time.time()
        self._stale_flags.clear()
        self._last_change.clear()

    def deactivate(self) -> None:
        """Deactivate startup mode — return to normal operation."""
        self.is_active = False
        self._activated_at = None
        self._stale_flags.clear()
        self._last_change.clear()

    def toggle(self, active: bool) -> None:
        """Set startup mode to a specific state."""
        if active:
            self.activate()
        else:
            self.deactivate()

    @property
    def mode_name(self) -> str:
        """Current mode as a string: 'STARTUP' or 'NORMAL'."""
        return "STARTUP" if self.is_active else "NORMAL"

    @property
    def tier_thresholds(self) -> dict[str, int]:
        """Get current tier thresholds based on mode."""
        return dict(self._startup_tiers) if self.is_active else dict(self._normal_tiers)

    @property
    def mass_balance_tolerance_multiplier(self) -> float:
        """
        Multiplier for mass-balance tolerance.
        0.5 in startup mode = tolerance tightened by 50%.
        1.0 in normal mode = no change.
        """
        return self._mass_balance_tolerance_multiplier if self.is_active else 1.0

    def check_stale_readings(
        self, readings: list[dict], now: float
    ) -> list[StaleReadingFlag]:
        """
        Check for stale readings (unchanged for > 8 minutes).
        Only active in startup mode.

        Args:
            readings: list of reading dicts from simulator
            now: current timestamp

        Returns:
            List of active (unacknowledged) stale reading flags.
        """
        if not self.is_active:
            return []

        stale = []
        for r in readings:
            sid = r["sensor_id"]
            value = r["value"]

            if sid not in self._last_change:
                self._last_change[sid] = (now, value)
                continue

            last_time, last_value = self._last_change[sid]

            # Check if value has changed (small epsilon for sensor noise)
            if abs(value - last_value) > 0.01:
                self._last_change[sid] = (now, value)
                # Clear stale flag if value changed
                self._stale_flags.pop(sid, None)
                continue

            # Value unchanged — check duration
            duration = now - last_time
            if duration >= self._stale_threshold_seconds:
                if sid not in self._stale_flags:
                    self._stale_flags[sid] = StaleReadingFlag(
                        sensor_id=sid,
                        duration_seconds=duration,
                        last_value=value,
                        timestamp=now,
                    )
                else:
                    # Update duration on existing flag
                    self._stale_flags[sid].duration_seconds = duration

                if not self._stale_flags[sid].acknowledged:
                    stale.append(self._stale_flags[sid])

        return stale

    def acknowledge_stale(self, sensor_id: str) -> bool:
        """
        Acknowledge a stale reading flag (operator manual verification).
        Returns True if a flag existed and was acknowledged.
        """
        if sensor_id in self._stale_flags:
            self._stale_flags[sensor_id].acknowledged = True
            return True
        return False

    def get_stale_flags(self) -> list[StaleReadingFlag]:
        """Return all active (unacknowledged) stale flags."""
        return [f for f in self._stale_flags.values() if not f.acknowledged]

    def to_dict(self) -> dict:
        """Serialize full startup mode state."""
        return {
            "mode": self.mode_name,
            "is_active": self.is_active,
            "activated_at": self._activated_at,
            "tier_thresholds": self.tier_thresholds,
            "mass_balance_tolerance_multiplier": self.mass_balance_tolerance_multiplier,
            "stale_threshold_seconds": self._stale_threshold_seconds if self.is_active else None,
            "stale_flags": [f.to_dict() for f in self.get_stale_flags()],
        }
