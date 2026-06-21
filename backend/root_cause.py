"""
root_cause.py — AI Root Cause Explainer for ConfidenceOS.

When a sensor confidence degrades, Claude analyses:
  - Current confidence breakdown (calibration, stability, cross-sensor, plausibility)
  - Recent confidence trend (last 2 hours from DB)
  - Causal graph position (upstream causes, downstream effects)

Returns a 3-sentence operator narrative:
  1. Why this anomaly likely occurred
  2. Sensor fault or process issue?
  3. What the operator should physically check first

Falls back to deterministic structured text when no LLM provider is configured.
Advisory only — confidence engine remains authoritative; never issues control commands.
"""

import json
import re

from llm_client import complete_text, is_configured, provider


async def explain_root_cause(
    sensor_id: str,
    confidence_data: dict,
    confidence_history: list[dict],
    causal_context: dict,
) -> dict:
    """
    Generate AI root cause explanation for a degraded sensor.

    Args:
        sensor_id: e.g. "LT-5100"
        confidence_data: latest entry from plant.latest_confidence[sensor_id]
        confidence_history: list of recent ConfidenceLog dicts (oldest first)
        causal_context: {"upstream": [...], "downstream": [...], "plant_name": str}

    Returns:
        {
          "ai_assisted": bool,
          "ai_label": str,
          "narrative": str,       # 3-sentence explanation
          "fault_class": str,     # "sensor_fault" | "process_issue" | "uncertain"
          "check_first": str,     # short operator action
          "confidence_pct": int,
          "model": str | None,
        }
    """
    if not is_configured():
        return _fallback(sensor_id, confidence_data, causal_context)

    try:
        return await _call_llm(sensor_id, confidence_data, confidence_history, causal_context)
    except Exception as exc:
        result = _fallback(sensor_id, confidence_data, causal_context)
        result["ai_error"] = str(exc)
        result["ai_label"] = "deterministic fallback (AI call failed); verify physically before acting"
        return result


async def _call_llm(
    sensor_id: str,
    confidence_data: dict,
    confidence_history: list[dict],
    causal_context: dict,
) -> dict:
    pct = confidence_data.get("confidence_pct", 0)
    tier = confidence_data.get("tier", "UNKNOWN")
    dominant = confidence_data.get("dominant_factor", "unknown")
    reasons = confidence_data.get("reasons", [])

    # Sub-scores give Claude the specific failure signature
    sub_parts = []
    for key, label in (
        ("calibration_score", "calibration"),
        ("stability_score", "stability"),
        ("cross_sensor_score", "cross-sensor"),
        ("plausibility_score", "plausibility"),
    ):
        val = confidence_data.get(key)
        if val is not None:
            sub_parts.append(f"{label}={val:.0%}")
    sub_score_text = ", ".join(sub_parts) if sub_parts else "not available"

    # Sample last 5 readings as a confidence trend line
    samples = confidence_history[-5:]
    trend_text = (
        " → ".join(f"{s['confidence_pct']}%" for s in samples)
        if samples else "no recent history"
    )

    upstream = causal_context.get("upstream", [])
    downstream = causal_context.get("downstream", [])
    plant_name = causal_context.get("plant_name", "industrial plant")

    system = (
        "You are ConfidenceOS, a read-only process monitoring AI. "
        "Advisory only — never issue control commands. "
        "End every explanation with: VERIFY PHYSICALLY BEFORE ACTING."
    )

    prompt = (
        f"Sensor: {sensor_id} | Plant: {plant_name}\n"
        f"Confidence: {pct}% (tier: {tier}, dominant: {dominant})\n"
        f"Reasons: {'; '.join(reasons) if reasons else 'none'}\n"
        f"Sub-scores: {sub_score_text}\n"
        f"Trend (oldest→newest): {trend_text}\n"
        f"Upstream: {', '.join(upstream[:4]) or 'none'} | Downstream: {', '.join(downstream[:4]) or 'none'}\n\n"
        f"Write exactly 3 operator sentences:\n"
        f"1. Why this anomaly likely occurred.\n"
        f"2. Sensor fault or process issue, and why.\n"
        f"3. What to physically check first.\n\n"
        f"Then output exactly this JSON on a new line (no fences):\n"
        f'{{\"fault_class\": \"sensor_fault\" or \"process_issue\" or \"uncertain\", '
        f'\"check_first\": \"short action\"}}\n\n'
        f"End 3rd sentence with: VERIFY PHYSICALLY BEFORE ACTING."
    )

    response = await complete_text(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=260,
        temperature=0.2,
    )
    text = response["text"].strip()

    structured = _extract_json(text)
    narrative = _clean_narrative(text)

    return {
        "ai_assisted": True,
        "ai_label": (
            f"AI root cause via {provider()}; advisory only; "
            "confidence engine authoritative; verify physically before acting"
        ),
        "narrative": narrative,
        "fault_class": structured.get("fault_class", "uncertain"),
        "check_first": structured.get(
            "check_first", "Verify reading against independent field instrument."
        ),
        "confidence_pct": pct,
        "model": response["model"],
    }


def _fallback(sensor_id: str, confidence_data: dict, causal_context: dict) -> dict:
    pct = confidence_data.get("confidence_pct", 0)
    dominant = confidence_data.get("dominant_factor", "unknown")
    reasons = confidence_data.get("reasons", [])
    upstream = causal_context.get("upstream", [])

    reasons_lower = " ".join(reasons).lower()

    if dominant == "calibration" or "calibration" in reasons_lower:
        narrative = (
            f"{sensor_id} confidence dropped to {pct}% due to calibration failure — "
            f"readings have drifted outside the expected calibration envelope. "
            f"This is a sensor instrument fault, not a real process change. "
            f"Check zero/span calibration records, transmitter wiring, and impulse line integrity "
            f"before taking any process action. VERIFY PHYSICALLY BEFORE ACTING."
        )
        fc = "sensor_fault"
        check = f"Inspect {sensor_id} calibration records and transmitter in the field."

    elif dominant == "stability" or any(w in reasons_lower for w in ("stuck", "freeze", "frozen", "stale")):
        narrative = (
            f"{sensor_id} has a frozen or stuck reading — the signal is not varying as expected, "
            f"reducing confidence to {pct}%. "
            f"This strongly indicates instrument failure or signal loss rather than a real process freeze. "
            f"Check transmitter power supply, signal cable continuity, and remote seal integrity. "
            f"VERIFY PHYSICALLY BEFORE ACTING."
        )
        fc = "sensor_fault"
        check = f"Inspect {sensor_id} transmitter power and signal cable continuity."

    elif upstream:
        cause = upstream[0]
        narrative = (
            f"{sensor_id} confidence degraded to {pct}%, likely propagated from an upstream "
            f"anomaly on {cause}. "
            f"This pattern suggests a real process disturbance rather than a local {sensor_id} instrument fault. "
            f"Verify {cause} reading first, then cross-check {sensor_id} against an independent field measurement. "
            f"VERIFY PHYSICALLY BEFORE ACTING."
        )
        fc = "process_issue"
        check = f"Verify upstream sensor {cause} before acting on {sensor_id}."

    else:
        cause_text = (
            f"Dominant factor: {dominant}. " if dominant not in ("unknown", "none", "") else ""
        )
        narrative = (
            f"{sensor_id} confidence has degraded to {pct}%. {cause_text}"
            f"Without AI analysis the root cause is uncertain — it may be sensor drift, fouling, or a process change. "
            f"Cross-check against an independent field instrument and consult maintenance if the reading cannot be confirmed. "
            f"VERIFY PHYSICALLY BEFORE ACTING."
        )
        fc = "uncertain"
        check = f"Cross-check {sensor_id} with an independent field instrument."

    return {
        "ai_assisted": False,
        "ai_label": (
            "deterministic fallback; AI unavailable (configure LLM_PROVIDER / API key); "
            "verify physically before acting"
        ),
        "narrative": narrative,
        "fault_class": fc,
        "check_first": check,
        "confidence_pct": pct,
        "model": None,
    }


def _extract_json(text: str) -> dict:
    """Pull the structured JSON block out of Claude's response."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    # Prefer the block that contains fault_class
    match = re.search(r'\{[^{}]*"fault_class"[^{}]*\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Fallback: any JSON object
    match = re.search(r"\{[^{}]+\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _clean_narrative(text: str) -> str:
    """Remove the trailing JSON block so only the 3-sentence narrative remains."""
    cleaned = re.sub(r'\{[^{}]*"fault_class"[^{}]*\}', "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?.*?```", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()
