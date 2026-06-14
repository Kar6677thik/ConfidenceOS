"""
tag_provider.py - Read-only tag provider abstraction for ConfidenceOS.

ConfidenceOS is a trust layer: it reads process tags and publishes confidence,
evidence, and decision-support metadata. It does not write control commands,
setpoints, controller modes, or acknowledgements back to the control system.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Iterable

from simulator import SensorSimulator


class TagProvider:
    """Base class for read-only industrial tag providers."""

    provider_id = "base"
    display_name = "Read-only tag provider"
    provider_type = "read_only"
    status = "abstract"
    read_only = True
    allows_control_writes = False

    def read_tags(self) -> list[dict]:
        raise NotImplementedError

    def write_tag(self, tag: str, value) -> None:
        raise PermissionError(
            "ConfidenceOS is read-only and does not write control commands, setpoints, or tag values."
        )

    def load_scenario(self, path: str | Path) -> None:
        return None

    def reset(self) -> None:
        return None

    def elapsed(self) -> float:
        return 0.0

    @property
    def tick_count(self) -> int:
        return 0

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "provider_type": self.provider_type,
            "status": self.status,
            "read_only": self.read_only,
            "allows_control_writes": self.allows_control_writes,
            "writes_supported": False,
            "control_writes_enabled": False,
        }


class SimulatorProvider(TagProvider):
    """Read-only adapter around the existing ConfidenceOS simulator."""

    provider_id = "simulator"
    display_name = "SimulatorProvider"
    provider_type = "simulator"
    status = "active"

    def __init__(self, simulator: SensorSimulator | None = None):
        self.simulator = simulator or SensorSimulator()

    def read_tags(self) -> list[dict]:
        return self.simulator.tick()

    def load_scenario(self, path: str | Path) -> None:
        self.simulator.load_scenario(path)

    def reset(self) -> None:
        self.simulator.reset()

    def elapsed(self) -> float:
        return self.simulator.elapsed()

    @property
    def tick_count(self) -> int:
        return self.simulator.tick_count


class CsvReplayProvider(TagProvider):
    """
    Simple read-only CSV replay provider.

    Expected columns: timestamp, sensor_id, sensor_type, value, unit,
    failure_mode. When no path is supplied it behaves as a placeholder.
    """

    provider_id = "csv_replay"
    display_name = "CsvReplayProvider"
    provider_type = "csv_replay"

    def __init__(self, source_path: str | Path | None = None, loop: bool = True):
        self.source_path = Path(source_path) if source_path else None
        self.loop = loop
        self._frames = self._load_frames(self.source_path) if self.source_path else []
        self._index = 0
        self._start_time = time.time()
        self.status = "ready" if self._frames else "placeholder"

    def read_tags(self) -> list[dict]:
        if not self._frames:
            return []
        if self._index >= len(self._frames):
            if not self.loop:
                return self._frames[-1]
            self._index = 0
        frame = self._frames[self._index]
        self._index += 1
        now = time.time()
        return [{**row, "timestamp": now} for row in frame]

    def reset(self) -> None:
        self._index = 0
        self._start_time = time.time()

    def elapsed(self) -> float:
        return time.time() - self._start_time

    @property
    def tick_count(self) -> int:
        return self._index

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload.update({
            "source_path": str(self.source_path) if self.source_path else None,
            "loaded_frames": len(self._frames),
        })
        return payload

    def _load_frames(self, source_path: Path | None) -> list[list[dict]]:
        if not source_path or not source_path.exists():
            return []
        rows = []
        with open(source_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(_coerce_csv_row(row))
        return _group_rows_by_timestamp(rows)


class OpcUaProvider(TagProvider):
    """Placeholder for a future read-only OPC UA subscription provider."""

    provider_id = "opcua"
    display_name = "OpcUaProvider"
    provider_type = "opcua"
    status = "placeholder_not_connected"

    def __init__(self, endpoint_url: str | None = None):
        self.endpoint_url = endpoint_url

    def read_tags(self) -> list[dict]:
        return []

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload.update({
            "endpoint_url": self.endpoint_url,
            "note": "Placeholder only. Future OPC UA support must remain subscription/read-only.",
        })
        return payload


def provider_catalog() -> list[dict]:
    return [
        SimulatorProvider().to_dict(),
        CsvReplayProvider().to_dict(),
        OpcUaProvider().to_dict(),
    ]


def _coerce_csv_row(row: dict) -> dict:
    value = row.get("value")
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    timestamp = row.get("timestamp")
    try:
        timestamp = float(timestamp)
    except (TypeError, ValueError):
        timestamp = 0.0
    return {
        "sensor_id": row.get("sensor_id", ""),
        "sensor_type": row.get("sensor_type", ""),
        "value": value,
        "unit": row.get("unit", ""),
        "timestamp": timestamp,
        "failure_mode": row.get("failure_mode") or None,
    }


def _group_rows_by_timestamp(rows: Iterable[dict]) -> list[list[dict]]:
    frames: list[list[dict]] = []
    frame_by_ts: dict[float, list[dict]] = {}
    for row in rows:
        frame_by_ts.setdefault(float(row.get("timestamp", 0.0)), []).append(row)
    for timestamp in sorted(frame_by_ts):
        frames.append(frame_by_ts[timestamp])
    return frames
