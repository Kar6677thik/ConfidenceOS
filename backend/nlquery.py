"""
nlquery.py — Natural Language Plant Query Interface for ConfidenceOS V2 (Module 8).

Lets anyone ask the system anything in plain English and get a grounded,
cited answer. Uses Claude API with strict grounding instructions.
Falls back to structured text if no API key is set.
"""

import os
import json
from datetime import datetime


PLANT_QUERY_SYSTEM_PROMPT = """You are ConfidenceOS, an industrial plant intelligence assistant for a control room operator.

RULES:
1. Answer the operator's question using ONLY the sensor data provided below.
2. Cite specific sensor IDs, confidence scores, timestamps, and values in your answer.
3. Never extrapolate beyond the data provided.
4. If you cannot answer from the available data, say so explicitly.
5. Keep answers concise (2-4 sentences) and in plain English — no jargon.
6. When discussing sensor reliability, always reference the confidence percentage and tier.
7. For safety questions, err on the side of caution.

You have access to:
- Live sensor readings with confidence scores
- Active mass-balance flags
- Recent anomalies
- Prediction data (if available)
"""


async def query_plant(
    question: str,
    live_state: dict,
    anomalies: list,
    predictions: dict = None,
) -> dict:
    """
    Answer a natural language question about plant state.
    
    Args:
        question: the user's question in plain English
        live_state: dict with readings, confidence, mass_balance, mode
        anomalies: list of recent anomaly dicts
        predictions: prediction data per sensor (optional)
    
    Returns:
        dict with 'answer', 'sources', and 'source_type' ('claude' or 'fallback')
    """
    # Build context string for the LLM
    context = _build_context(live_state, anomalies, predictions)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    
    if api_key:
        try:
            return await _query_claude(question, context, api_key)
        except Exception as e:
            print(f"[NLQuery] Claude API error: {e}, falling back to structured response")

    # Fallback: structured text response
    return _fallback_response(question, live_state, anomalies, predictions)


async def _query_claude(question: str, context: str, api_key: str) -> dict:
    """Query Claude API with grounded context."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=PLANT_QUERY_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"""PLANT DATA:
{context}

OPERATOR QUESTION:
{question}"""
            }
        ],
    )

    answer = message.content[0].text if message.content else "Unable to generate response."

    return {
        "answer": answer,
        "source_type": "claude",
        "sources": _extract_sources(answer, context),
    }


def _build_context(live_state: dict, anomalies: list, predictions: dict = None) -> str:
    """Build a structured context string for the LLM."""
    sections = []

    # Sensor readings with confidence
    sections.append("=== CURRENT SENSOR READINGS ===")
    readings = live_state.get("readings", [])
    confidence = live_state.get("confidence", [])
    conf_map = {c.get("sensor_id"): c for c in confidence}

    for r in readings:
        sid = r.get("sensor_id", "?")
        val = r.get("value", "?")
        unit = r.get("unit", "")
        c = conf_map.get(sid, {})
        pct = c.get("confidence_pct", "?")
        tier = c.get("tier", "?")
        reasons = c.get("reasons", [])
        reason_str = "; ".join(reasons[:2]) if reasons else "N/A"
        sections.append(f"  {sid}: {val} {unit} | Confidence: {pct}% ({tier}) | {reason_str}")

    # Mass-balance state
    mb = live_state.get("mass_balance", {})
    if mb:
        sections.append("\n=== MASS-BALANCE STATE ===")
        sections.append(f"  Implied level: {mb.get('implied_level', '?')} ft")
        sections.append(f"  Measured level: {mb.get('measured_level', '?')} ft")
        sections.append(f"  Discrepancy: {mb.get('discrepancy', '?')} ft")
        flags = mb.get("flags", [])
        if flags:
            for f in flags:
                sections.append(f"  FLAG: {f.get('severity', '?')} — {f.get('message', '')}")
        else:
            sections.append("  No active flags.")

    # Operating mode
    mode = live_state.get("mode", {})
    if mode:
        sections.append(f"\n=== OPERATING MODE ===")
        sections.append(f"  Mode: {mode.get('mode', 'NORMAL')}")
        if mode.get("is_active"):
            sections.append("  Startup mode is ACTIVE — heightened scrutiny enabled.")

    # Recent anomalies
    if anomalies:
        sections.append("\n=== RECENT ANOMALIES (last 24h) ===")
        for a in anomalies[:10]:
            sections.append(f"  [{a.get('severity', '?')}] {a.get('sensor_id', '?')}: {a.get('description', '')} ({a.get('timestamp', '')})")

    # Predictions
    if predictions:
        sections.append("\n=== PREDICTIVE FORECASTS ===")
        for sid, p in predictions.items():
            if p.get("time_to_low_hours") is not None:
                sections.append(f"  {sid}: predicted LOW in ~{p['time_to_low_hours']}h, CRITICAL in ~{p.get('time_to_critical_hours', '?')}h")
                if p.get("recommended_action"):
                    sections.append(f"    → {p['recommended_action']}")
            elif p.get("model_fit") == "insufficient":
                sections.append(f"  {sid}: insufficient data for prediction")
            else:
                sections.append(f"  {sid}: stable — no threshold crossing predicted")

    return "\n".join(sections)


def _fallback_response(question: str, live_state: dict, anomalies: list, predictions: dict = None) -> dict:
    """Generate a structured text response without the LLM."""
    q = question.lower()
    readings = live_state.get("readings", [])
    confidence = live_state.get("confidence", [])
    conf_map = {c.get("sensor_id"): c for c in confidence}
    mb = live_state.get("mass_balance", {})

    sources = []

    # "Why is X flagged?"
    for c in confidence:
        sid = c.get("sensor_id", "")
        if sid.lower() in q or "flagged" in q or "why" in q:
            if c.get("tier") in ("LOW", "CRITICAL", "MEDIUM"):
                reasons = c.get("reasons", ["No specific reason available."])
                answer = f"{sid} is at {c['confidence_pct']:.0f}% confidence ({c['tier']}). "
                answer += "Reasons: " + "; ".join(reasons[:3]) + "."
                sources.append({"sensor_id": sid, "confidence_pct": c["confidence_pct"], "tier": c["tier"]})
                return {"answer": answer, "source_type": "fallback", "sources": sources}

    # "Mass balance" questions
    if "mass" in q or "balance" in q or "discrepancy" in q:
        disc = mb.get("discrepancy", 0)
        impl = mb.get("implied_level", 0)
        meas = mb.get("measured_level", 0)
        flags = mb.get("flags", [])
        answer = f"Current mass-balance: implied level = {impl:.1f} ft, measured level = {meas:.1f} ft, discrepancy = {disc:.2f} ft. "
        if flags:
            answer += f"Active flag: {flags[0].get('severity', '?')} — {flags[0].get('message', '')}."
        else:
            answer += "No active flags — flows are balanced within tolerance."
        return {"answer": answer, "source_type": "fallback", "sources": sources}

    # "Which sensor" / "worst" / "lowest"
    if "which" in q or "worst" in q or "lowest" in q or "most degraded" in q:
        sorted_conf = sorted(confidence, key=lambda c: c.get("confidence_pct", 100))
        if sorted_conf:
            worst = sorted_conf[0]
            answer = f"The sensor with the lowest confidence is {worst['sensor_id']} at {worst['confidence_pct']:.0f}% ({worst['tier']})."
            if worst.get("reasons"):
                answer += f" Reason: {worst['reasons'][0]}."
            sources.append({"sensor_id": worst["sensor_id"], "confidence_pct": worst["confidence_pct"]})
            return {"answer": answer, "source_type": "fallback", "sources": sources}

    # "Safe" / "risk" questions
    if "safe" in q or "risk" in q:
        low_sensors = [c for c in confidence if c.get("tier") in ("LOW", "CRITICAL")]
        if low_sensors:
            names = ", ".join(c["sensor_id"] for c in low_sensors)
            answer = f"Caution advised. {len(low_sensors)} sensor(s) have degraded confidence: {names}. "
            answer += "Manual verification is recommended before making operational changes."
        else:
            answer = "All sensors are currently at HIGH or MEDIUM confidence. No critical flags active. "
            if mb.get("flags"):
                answer += "However, there is an active mass-balance flag — verify flow readings."
            else:
                answer += "The system appears to be operating normally."
        return {"answer": answer, "source_type": "fallback", "sources": sources}

    # "Prediction" / "when" / "forecast"
    if predictions and ("predict" in q or "when" in q or "forecast" in q or "calibration" in q):
        urgent = []
        for sid, p in predictions.items():
            if p.get("time_to_low_hours") is not None:
                urgent.append((sid, p))
        if urgent:
            urgent.sort(key=lambda x: x[1].get("time_to_low_hours", 999))
            sid, p = urgent[0]
            answer = f"{sid} is predicted to reach LOW confidence in ~{p['time_to_low_hours']:.0f} hours. "
            if p.get("recommended_action"):
                answer += p["recommended_action"]
            return {"answer": answer, "source_type": "fallback", "sources": sources}
        else:
            return {"answer": "No sensors are currently on a degradation trajectory toward LOW or CRITICAL confidence.", "source_type": "fallback", "sources": sources}

    # General status
    avg_conf = sum(c.get("confidence_pct", 100) for c in confidence) / len(confidence) if confidence else 100
    high_count = sum(1 for c in confidence if c.get("tier") == "HIGH")
    answer = f"Plant overview: {len(readings)} sensors active, average confidence {avg_conf:.0f}%. "
    answer += f"{high_count} sensors at HIGH confidence. "
    if mb.get("flags"):
        answer += f"Mass-balance warning active (discrepancy: {mb.get('discrepancy', 0):.1f} ft)."
    else:
        answer += "No mass-balance flags. System operating normally."

    return {"answer": answer, "source_type": "fallback", "sources": sources}


def _extract_sources(answer: str, context: str) -> list:
    """Extract sensor IDs mentioned in the answer as source citations."""
    import re
    sensor_ids = re.findall(r'[A-Z]{2}-\d{4}', answer)
    return [{"sensor_id": sid} for sid in set(sensor_ids)]
