"""
handover.py — Shift Handover Brief Generator for ConfidenceOS (Module 6).

The CSB investigation found that the night shift operator at Texas City did
not communicate the faulty high-level alarm to the incoming day shift. This
module makes silent handover impossible by auto-generating a comprehensive,
LLM-polished shift brief from live system state.

Uses Claude API (claude-sonnet-4-20250514) for natural language generation.
Falls back to a structured template brief when no API key is configured.

PRD Reference: §4.6
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Optional


# ─── Configuration ───────────────────────────────────────────────────────────

CLAUDE_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """\
You are a safety-critical industrial system generating a shift handover brief \
for an incoming plant operator. The operator is about to take control of a \
potentially hazardous process system.

Your brief must be:
- Written in clear, plain English — no jargon, no raw numbers without context
- Organized into clear sections
- Actionable — every issue must have a recommended verification step
- Honest about uncertainty — if a sensor is degraded, say so plainly

Format the brief with these sections:
1. OVERALL PLANT STATUS — one-sentence summary of current plant health
2. DEGRADED SENSORS — any sensor below HIGH confidence, with explanation
3. MASS-BALANCE STATUS — any physical inconsistency flags
4. ANOMALIES THIS SHIFT — significant events during the shift
5. RECOMMENDED ACTIONS — specific verifications the incoming operator should \
complete before taking control

Be concise but thorough. The operator's life may depend on this information \
being clear and complete.\
"""


# ─── Shift Handover Brief Generator ─────────────────────────────────────────

class HandoverBriefGenerator:
    """
    Collects system state and generates a natural-language shift handover brief.

    Uses Claude API when ANTHROPIC_API_KEY is set. Falls back to a structured
    template brief otherwise.

    Usage:
        gen = HandoverBriefGenerator()
        state = gen.collect_system_state(confidence, mb, anomalies, mode)
        brief = await gen.generate_brief(state)
    """

    def __init__(self):
        self._latest_brief: Optional[dict] = None
        self._latest_timestamp: Optional[float] = None

    def collect_system_state(
        self,
        confidence_data: list[dict],
        mass_balance_state: dict,
        anomalies: list[dict],
        mode_state: dict,
        plant_context: Optional[dict] = None,
        incidents: Optional[list[dict]] = None,
    ) -> dict:
        """
        Assemble structured system state snapshot for brief generation.

        Args:
            confidence_data: list of confidence result dicts (from ConfidenceEngine)
            mass_balance_state: MassBalanceState.to_dict() output
            anomalies: list of anomaly log dicts
            mode_state: StartupManager.to_dict() output

        Returns:
            Structured dict ready for prompt building.
        """
        degraded = [
            c for c in confidence_data
            if c.get("tier") in ("MEDIUM", "LOW", "CRITICAL")
        ]
        high_confidence = [
            c for c in confidence_data
            if c.get("tier") == "HIGH"
        ]

        flags = mass_balance_state.get("flags", [])

        return {
            "timestamp": time.time(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode_state.get("mode", "NORMAL"),
            "total_sensors": len(confidence_data),
            "healthy_sensors": len(high_confidence),
            "degraded_sensors": degraded,
            "mass_balance": {
                "implied_level": mass_balance_state.get("implied_level"),
                "measured_level": mass_balance_state.get("measured_level"),
                "discrepancy": mass_balance_state.get("discrepancy"),
                "implied_delta": mass_balance_state.get("implied_delta"),
                "measured_delta": mass_balance_state.get("measured_delta"),
                "flags": flags,
            },
            "anomalies": anomalies[-20:],  # Last 20 anomalies
            "stale_flags": mode_state.get("stale_flags", []),
            "plant_context": plant_context or {},
            "incidents": incidents or [],
        }

    async def generate_brief(self, system_state: dict) -> dict:
        """
        Generate a shift handover brief.

        Uses Claude API if ANTHROPIC_API_KEY is configured and valid.
        Falls back to structured template otherwise.

        Returns:
            Dict with keys: source, model, generated_at, brief, system_state_summary
        """
        api_key = os.getenv("ANTHROPIC_API_KEY", "")

        if not api_key or api_key == "your_anthropic_api_key_here":
            brief = self._fallback_brief(system_state)
        else:
            try:
                brief = await self._call_claude(system_state, api_key)
            except Exception as e:
                brief = self._fallback_brief(system_state)
                brief["generation_error"] = str(e)
                brief["source"] = "fallback (API error)"

        self._latest_brief = brief
        self._latest_timestamp = time.time()
        return brief

    async def _call_claude(self, system_state: dict, api_key: str) -> dict:
        """Call Claude API to generate a natural-language handover brief."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)

        user_message = self._build_user_message(system_state)

        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        brief_text = response.content[0].text

        return {
            "source": "claude",
            "model": CLAUDE_MODEL,
            "generated_at": system_state["generated_at"],
            "brief": brief_text,
            "system_state_summary": self._build_summary(system_state),
        }

    def _build_user_message(self, state: dict) -> str:
        """Construct the user message for Claude from system state."""
        lines = [
            "Generate a shift handover brief for the following plant state.",
            f"Current mode: {state['mode']}",
            f"Time: {state['generated_at']}",
            "",
            f"SENSOR CONFIDENCE STATUS ({state['total_sensors']} sensors):",
            f"  Healthy (HIGH confidence): {state['healthy_sensors']}",
            f"  Degraded: {len(state['degraded_sensors'])}",
        ]

        for s in state["degraded_sensors"]:
            lines.append(
                f"  - {s['sensor_id']}: {s['confidence_pct']}% ({s['tier']})"
            )
            for reason in s.get("reasons", []):
                lines.append(f"    → {reason}")

        context = state.get("plant_context") or {}
        incidents = state.get("incidents") or []
        if context or incidents:
            lines.append("")
            lines.append("ACTIVE ADVISORY CONTEXT:")
            if context:
                lines.append(f"  State: {context.get('state', 'UNKNOWN')} ({context.get('severity', 'INFO')})")
                lines.append(f"  Operator focus: {context.get('operator_focus', 'Review current advisory state.')}")
            for incident in incidents[:5]:
                lines.append(
                    f"  INCIDENT [{incident.get('severity', 'INFO')}] "
                    f"{incident.get('title', 'Advisory incident')}: "
                    f"{incident.get('summary', '')}"
                )
                lines.append(f"    First action: {incident.get('first_action', 'Review evidence stack.')}")

        lines.append("")
        lines.append("MASS-BALANCE STATUS:")
        mb = state["mass_balance"]
        if mb.get("implied_level") is not None:
            lines.append(f"  Implied level (from flows): {mb['implied_level']} ft")
            lines.append(f"  Measured level (from sensor): {mb['measured_level']} ft")
            lines.append(f"  Discrepancy: {mb['discrepancy']} ft")

        if mb["flags"]:
            for f in mb["flags"]:
                lines.append(f"  FLAG [{f['severity']}]: {f['message']}")
        else:
            lines.append("  No physical inconsistency flags active.")

        if state["anomalies"]:
            lines.append("")
            lines.append(
                f"ANOMALIES DURING SHIFT ({len(state['anomalies'])} events):"
            )
            for a in state["anomalies"][-10:]:  # Last 10 for prompt brevity
                lines.append(
                    f"  [{a.get('severity', 'INFO')}] "
                    f"{a.get('sensor_id', '?')}: "
                    f"{a.get('description', a.get('anomaly_type', '?'))}"
                )

        if state["stale_flags"]:
            lines.append("")
            lines.append("STALE READING FLAGS (Startup Mode):")
            for sf in state["stale_flags"]:
                lines.append(
                    f"  - {sf['sensor_id']}: unchanged for "
                    f"{sf['duration_seconds']:.0f}s"
                )

        return "\n".join(lines)

    def _fallback_brief(self, state: dict) -> dict:
        """
        Generate a structured handover brief without the Claude API.
        Used when ANTHROPIC_API_KEY is not configured or when the API call fails.
        """
        sections = []

        # ── Section 1: Overall status
        degraded_count = len(state["degraded_sensors"])
        total = state["total_sensors"]
        mb_flags = state["mass_balance"]["flags"]

        if degraded_count == 0 and not mb_flags:
            sections.append(
                "## 1. OVERALL PLANT STATUS\n\n"
                "All sensors operating within normal confidence parameters. "
                "No mass-balance inconsistencies. No immediate concerns."
            )
        elif degraded_count > 0 and mb_flags:
            sections.append(
                f"## 1. OVERALL PLANT STATUS\n\n"
                f"⚠ **ATTENTION REQUIRED** — {degraded_count} of {total} sensors "
                f"have degraded confidence AND mass-balance inconsistency detected. "
                f"Manual verification required before taking control."
            )
        elif degraded_count > 0:
            sections.append(
                f"## 1. OVERALL PLANT STATUS\n\n"
                f"⚠ {degraded_count} of {total} sensors have degraded confidence. "
                f"Review sensor details below before taking control."
            )
        else:
            sections.append(
                f"## 1. OVERALL PLANT STATUS\n\n"
                f"All sensors at HIGH confidence, but mass-balance inconsistency "
                f"detected. Investigate flow/level discrepancy."
            )

        # ── Section 2: Degraded sensors
        if state["degraded_sensors"]:
            lines = ["## 2. DEGRADED SENSORS"]
            for s in state["degraded_sensors"]:
                lines.append(
                    f"\n**{s['sensor_id']}** — Confidence: "
                    f"{s['confidence_pct']}% ({s['tier']})"
                )
                for reason in s.get("reasons", []):
                    lines.append(f"  - {reason}")
            sections.append("\n".join(lines))
        else:
            sections.append(
                "## 2. DEGRADED SENSORS\n\nNone — all sensors at HIGH confidence."
            )

        # ── Section 3: Mass-balance status
        mb = state["mass_balance"]
        mb_lines = ["## 3. MASS-BALANCE STATUS"]

        if mb.get("implied_level") is not None:
            mb_lines.append(
                f"\n- Implied level (from flow integration): {mb['implied_level']} ft"
            )
            mb_lines.append(f"- Measured level (from LT sensor): {mb['measured_level']} ft")
            mb_lines.append(f"- Discrepancy: {mb['discrepancy']} ft")

        if mb_flags:
            mb_lines.append("")
            for f in mb_flags:
                mb_lines.append(f"⚠ **{f['severity']}**: {f['message']}")
        else:
            mb_lines.append(
                "\nNo physical inconsistency flags. Mass-balance within tolerance."
            )
        sections.append("\n".join(mb_lines))

        # ── Section 4: Anomalies
        if state["anomalies"]:
            a_lines = [
                f"## 4. ANOMALIES THIS SHIFT ({len(state['anomalies'])} events)"
            ]
            for a in state["anomalies"][-10:]:
                a_lines.append(
                    f"- [{a.get('severity', 'INFO')}] {a.get('sensor_id', '?')}: "
                    f"{a.get('description', a.get('anomaly_type', ''))}"
                )
            sections.append("\n".join(a_lines))
        else:
            sections.append(
                "## 4. ANOMALIES THIS SHIFT\n\nNo anomalies recorded during this shift."
            )

        # ── Section 5: Recommended actions
        incidents = state.get("incidents") or []
        if incidents:
            incident_lines = ["## 5. ACTIVE INCIDENTS / REQUIRED ACTIONS"]
            for incident in incidents:
                sensors = ", ".join(incident.get("affected_sensors", [])) or "SYSTEM"
                incident_lines.append(
                    f"\n**{incident.get('title', 'Advisory incident')}** "
                    f"[{incident.get('severity', 'INFO')}]"
                )
                incident_lines.append(f"- Affected: {sensors}")
                incident_lines.append(f"- Summary: {incident.get('summary', '')}")
                incident_lines.append(f"- First action: {incident.get('first_action', 'Review evidence stack.')}")
            sections.append("\n".join(incident_lines))

        actions = ["## 6. RECOMMENDED ACTIONS" if incidents else "## 5. RECOMMENDED ACTIONS"]
        has_actions = False

        for incident in incidents:
            has_actions = True
            actions.append(
                f"- {incident.get('title', 'Incident')}: {incident.get('first_action', 'Review evidence stack.')}"
            )

        if state["degraded_sensors"]:
            for s in state["degraded_sensors"]:
                has_actions = True
                if s["tier"] == "CRITICAL":
                    actions.append(
                        f"- **MANDATORY**: Manually verify {s['sensor_id']} with "
                        f"independent measurement (sight glass, field transmitter) "
                        f"before taking control."
                    )
                elif s["tier"] == "LOW":
                    actions.append(
                        f"- Cross-verify {s['sensor_id']} against adjacent sensor "
                        f"readings. Schedule calibration if degradation persists."
                    )
                else:
                    actions.append(
                        f"- Monitor {s['sensor_id']} closely. Schedule calibration "
                        f"if confidence continues to degrade."
                    )

        if mb_flags:
            has_actions = True
            actions.append(
                "- Investigate mass-balance discrepancy: compare flow totalizer "
                "readings with manual level check via sight glass."
            )

        if state["stale_flags"]:
            has_actions = True
            for sf in state["stale_flags"]:
                actions.append(
                    f"- Verify {sf['sensor_id']} is not stuck: reading unchanged "
                    f"for {sf['duration_seconds']:.0f} seconds."
                )

        if not has_actions:
            actions.append(
                "- No specific actions required. Continue normal monitoring."
            )

        sections.append("\n".join(actions))

        brief_text = "\n\n".join(sections)

        return {
            "source": "fallback",
            "model": None,
            "generated_at": state["generated_at"],
            "brief": brief_text,
            "system_state_summary": self._build_summary(state),
        }

    def _build_summary(self, state: dict) -> dict:
        """Build a compact summary of the system state for the response."""
        return {
            "mode": state["mode"],
            "total_sensors": state["total_sensors"],
            "healthy_sensors": state["healthy_sensors"],
            "degraded_count": len(state["degraded_sensors"]),
            "anomaly_count": len(state["anomalies"]),
            "mass_balance_flags": len(state["mass_balance"]["flags"]),
            "plant_context": state.get("plant_context") or {},
            "incidents": state.get("incidents") or [],
        }

    @property
    def latest_brief(self) -> Optional[dict]:
        """Return the most recently generated brief, or None."""
        return self._latest_brief

    @property
    def latest_timestamp(self) -> Optional[float]:
        """Timestamp of the last generated brief."""
        return self._latest_timestamp
