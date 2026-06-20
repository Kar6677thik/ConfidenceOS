"""
deps.py — shared application singletons for FastAPI dependency injection.

Extracted from main.py so routers can import plant_manager and locks
without creating circular imports.
"""

import asyncio
import os

from plants import PlantManager

plant_manager = PlantManager()

# Anomaly deduplication: (plant_id:sensor_id:anomaly_type) → last-logged timestamp
anomaly_cooldown: dict[str, float] = {}
ANOMALY_COOLDOWN_SECONDS = 60.0

# Confidence logging throttle
_confidence_log_counter: dict[str, int] = {}
CONFIDENCE_LOG_INTERVAL = max(1, int(os.getenv("CONFIDENCEOS_CONFIDENCE_LOG_INTERVAL", "10")))
PERSIST_READINGS_INTERVAL = max(1, int(os.getenv("CONFIDENCEOS_PERSIST_READINGS_INTERVAL", "10")))
VERIFICATION_SYNC_INTERVAL = max(1, int(os.getenv("CONFIDENCEOS_VERIFICATION_SYNC_INTERVAL", "5")))

plant_loop_status: dict[str, dict] = {}

# Serialize all plant-loop DB writes through one in-process lock
db_write_lock = asyncio.Lock()
