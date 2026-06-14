"""
shift_channel.py - Persistent shift channel from operational debt and notes.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path


STATE_PATH = Path(__file__).with_name("shift_channel_state.json")


def build_shift_channel(plant_id: str, plant) -> dict:
    notes = _load_notes()
    debt = plant.latest_handover_debt or {}
    incidents = plant.latest_incidents or []
    tokens = plant.verification_tokens or []
    timeline = plant.latest_incident_timeline or []
    confidence_debt = plant.latest_confidence_debt or []

    pinned = []
    for incident in incidents:
        if incident.get("handover_required"):
            pinned.append({
                "id": f"incident:{incident.get('incident_id')}",
                "type": "unresolved_situation",
                "title": incident.get("title"),
                "severity": incident.get("severity", "WARNING"),
                "summary": incident.get("summary"),
                "operating_basis": incident.get("action_contract", {}),
            })
    for entry in debt.get("entries", []):
        pinned.append({
            "id": entry.get("id"),
            "type": entry.get("type"),
            "title": entry.get("title"),
            "severity": entry.get("severity", "WARNING"),
            "required_action": entry.get("required_action"),
        })

    thread = []
    for event in timeline[-12:]:
        thread.append({
            "id": event.get("event_id"),
            "type": event.get("event_type"),
            "author": "ConfidenceOS",
            "timestamp": event.get("timestamp"),
            "message": event.get("message"),
            "severity": event.get("severity", "INFO"),
        })
    for note in notes:
        if note.get("plant_id") == plant_id:
            thread.append(note)
    thread.sort(key=lambda item: item.get("timestamp", 0), reverse=True)

    return {
        "plant_id": plant_id,
        "channel_id": f"{plant_id}:shift-channel",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pinned": pinned,
        "thread": thread[:30],
        "summary": _summary(pinned, tokens, confidence_debt),
        "handover_debt": debt,
        "verification_tokens": tokens,
        "confidence_debt": confidence_debt,
    }


def add_note(plant_id: str, author: str, message: str) -> dict:
    state = _load_state()
    note = {
        "id": f"note:{int(time.time() * 1000)}",
        "type": "operator_note",
        "plant_id": plant_id,
        "author": author or "Operator",
        "message": message,
        "timestamp": time.time(),
        "severity": "INFO",
        "handover_required": True,
    }
    state.setdefault("notes", []).append(note)
    _save_state(state)
    return note


def reset_notes() -> dict:
    state = {"notes": []}
    _save_state(state)
    return state


def _summary(pinned: list[dict], tokens: list[dict], confidence_debt: list[dict]) -> str:
    if pinned:
        return f"{len(pinned)} unresolved operating-basis item(s) pinned for handover."
    if tokens:
        return f"{len(tokens)} verification token(s) active or recently created."
    if confidence_debt:
        return "Confidence debt is being tracked for maintenance priority."
    return "No unresolved handover debt currently pinned."


def _load_notes() -> list[dict]:
    return _load_state().get("notes", [])


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"notes": []}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
