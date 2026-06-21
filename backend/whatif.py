"""
whatif.py — What-If Trust Propagation for ConfidenceOS.

Given a hypothetical confidence level for one sensor, traverses the causal
graph and estimates how the degradation would cascade to downstream sensors.
AI layer (Claude) explains the scenario in operator/engineer terms.

Falls back to deterministic cascade estimation when no LLM key is set.
Advisory only — confidence engine remains authoritative.
"""

from __future__ import annotations

from llm_client import complete_text, is_configured, provider


async def simulate_what_if(
    sensor_id: str,
    what_if_pct: int,
    plant_confidence: dict,
    graph: dict,
) -> dict:
    """
    Simulate confidence cascade if sensor_id drops to what_if_pct%.

    Args:
        sensor_id:        e.g. "LT-5100"
        what_if_pct:      hypothetical confidence percent (0-100)
        plant_confidence: dict of {sensor_id: confidence_data} from latest tick
        graph:            causal graph dict with "edges" list and "plant_name"

    Returns:
        {
          "sensor_id": str,
          "what_if_pct": int,
          "current_pct": int,
          "affected": [{"sensor_id", "current_pct", "estimated_pct",
                        "estimated_impact", "severity"}],
          "narrative": str,
          "ai_assisted": bool,
          "ai_label": str,
          "model": str | None,
        }
    """
    edges = graph.get("edges", [])
    plant_name = graph.get("plant_name", "process unit")

    current_conf = plant_confidence.get(sensor_id, {})
    current_pct = int(current_conf.get("confidence_pct", 100))

    affected = _propagate_downstream(sensor_id, what_if_pct, edges, plant_confidence)

    scenario = {
        "sensor_id": sensor_id,
        "what_if_pct": what_if_pct,
        "current_pct": current_pct,
        "affected": affected,
    }

    if not is_configured():
        return {**scenario, **_fallback_narrative(sensor_id, what_if_pct, affected, plant_name)}

    try:
        ai_result = await _call_llm(scenario, plant_name)
        return {**scenario, **ai_result}
    except Exception as exc:
        fallback = _fallback_narrative(sensor_id, what_if_pct, affected, plant_name)
        return {
            **scenario,
            **fallback,
            "ai_error": str(exc),
            "ai_label": "deterministic fallback (AI call failed); verify physically before acting",
        }


def _propagate_downstream(
    sensor_id: str,
    what_if_pct: int,
    edges: list[dict],
    plant_confidence: dict,
) -> list[dict]:
    """BFS through causal edges; estimate confidence impact on each downstream sensor."""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            adjacency.setdefault(src, []).append(tgt)

    visited: set[str] = set()
    # queue: (current_sensor, propagated_pct_at_this_hop)
    queue: list[tuple[str, int]] = [(sensor_id, what_if_pct)]
    affected: list[dict] = []

    while queue:
        current, propagated_pct = queue.pop(0)
        for downstream in adjacency.get(current, []):
            if downstream in visited or downstream == sensor_id:
                continue
            visited.add(downstream)

            conf_data = plant_confidence.get(downstream, {})
            current_pct = int(conf_data.get("confidence_pct", 100))

            # Impact dampens 40% per hop (energy loss through the causal chain)
            delta = propagated_pct - 100
            estimated_new = max(0, min(100, current_pct + int(delta * 0.6)))
            estimated_impact = estimated_new - current_pct

            if estimated_impact >= 0:
                # No degradation at this hop — stop propagating
                continue

            severity = (
                "CRITICAL" if estimated_new < 20
                else "LOW" if estimated_new < 50
                else "DEGRADED" if estimated_new < 80
                else "NOMINAL"
            )

            affected.append({
                "sensor_id": downstream,
                "current_pct": current_pct,
                "estimated_pct": estimated_new,
                "estimated_impact": estimated_impact,
                "severity": severity,
            })

            queue.append((downstream, estimated_new))

    return affected


def _fallback_narrative(
    sensor_id: str,
    what_if_pct: int,
    affected: list[dict],
    plant_name: str,
) -> dict:
    if not affected:
        narrative = (
            f"If {sensor_id} confidence fell to {what_if_pct}%, "
            f"no downstream sensors in {plant_name} would be directly impacted "
            f"based on the current causal graph. "
            f"Verify {sensor_id} independently. ADVISORY — verify physically before acting."
        )
    else:
        critical = [s for s in affected if s["severity"] == "CRITICAL"]
        count = len(affected)
        impact_summary = (
            f"{count} downstream sensor{'s' if count > 1 else ''} affected"
            + (f" — {len(critical)} entering critical range" if critical else "")
        )
        first = affected[0]
        narrative = (
            f"If {sensor_id} confidence fell to {what_if_pct}%, "
            f"{impact_summary} in {plant_name}. "
            f"{first['sensor_id']} would be most directly impacted, "
            f"dropping to approximately {first['estimated_pct']}% confidence. "
            f"Verify {sensor_id} physically and consider field cross-checks on "
            f"affected sensors before relying on their readings. "
            f"ADVISORY — verify physically before acting on this scenario."
        )

    return {
        "narrative": narrative,
        "ai_assisted": False,
        "ai_label": (
            "deterministic cascade analysis; AI unavailable "
            "(configure LLM provider to activate AI narrative)"
        ),
        "model": None,
    }


async def _call_llm(scenario: dict, plant_name: str) -> dict:
    affected = scenario["affected"]
    sensor_id = scenario["sensor_id"]
    what_if_pct = scenario["what_if_pct"]
    current_pct = scenario["current_pct"]

    affected_lines = "\n".join(
        f"  {s['sensor_id']}: {s['current_pct']}% → ~{s['estimated_pct']}% ({s['severity']})"
        for s in affected[:6]
    ) or "  none detected in current graph"

    system = (
        "You are ConfidenceOS, a read-only industrial process monitoring AI. "
        "You help engineers understand hypothetical cascade failures in a process plant. "
        "You never issue control commands — your analysis is advisory and scenario-based only. "
        "Be specific about which sensors to watch and why the cascade matters operationally."
    )

    prompt = (
        f"Plant: {plant_name}\n"
        f"What-If Scenario: {sensor_id} confidence drops from {current_pct}% to {what_if_pct}%\n"
        f"Estimated cascade (deterministic graph propagation):\n{affected_lines}\n\n"
        f"Write exactly 3 sentences for an engineer:\n"
        f"Sentence 1: What physical failure mode would drive {sensor_id} to {what_if_pct}% "
        f"confidence, and what that level means for operator trust.\n"
        f"Sentence 2: How the cascade propagates through the process — name the most at-risk "
        f"downstream sensor and why.\n"
        f"Sentence 3: What the engineer should monitor or pre-position to mitigate "
        f"this scenario if it becomes real.\n\n"
        f"End with: ADVISORY — verify physically before acting on this scenario."
    )

    response = await complete_text(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=320,
        temperature=0.2,
    )

    return {
        "narrative": response["text"].strip(),
        "ai_assisted": True,
        "ai_label": (
            f"AI cascade analysis via {provider()}; "
            "advisory only; confidence engine authoritative; verify physically before acting"
        ),
        "model": response["model"],
    }
