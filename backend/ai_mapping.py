"""
ai_mapping.py — AI-assisted tag mapping and template suggestion for ConfidenceOS.

This module adds genuine AI capability to the HMI Compiler pipeline:

  1. explain_mapping()    — Claude writes evidence/counter-evidence narrative for a
                            deterministic mapping proposal. The deterministic rule
                            remains authoritative; Claude explains it in depth.

  2. parse_arbitrary_tags() — Claude proposes canonical bindings for an *arbitrary*
                              pasted tag list (not just the demo fixture). Every
                              proposal is funnelled back through the existing
                              Mapping Court + engineer approval flow.

  3. suggest_template()   — Given a plain-English asset description, Claude returns
                            a template assignment chosen from the closed set of real
                            templates in equipment_templates.json. The compiler
                            validates; engineer approves before any publish.

Guardrails (all AI output is advisory only):
  - Every proposal goes through the deterministic Mapping Court and template
    validation before it can be published.
  - Engineer approval is always required.
  - ConfidenceOS never writes tag values, setpoints, or control commands.
  - When ANTHROPIC_API_KEY is absent, all functions fall back to deterministic
    behaviour and return ai_assisted=False with an honest label.

Pattern mirrors backend/handover.py (_call_claude / _fallback_brief).
"""

import json
import os
import re
from typing import Optional

CLAUDE_MODEL = "claude-sonnet-4-6"

_AI_AVAILABLE: Optional[bool] = None


def _api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "")


def _ai_available() -> bool:
    global _AI_AVAILABLE
    if _AI_AVAILABLE is None:
        key = _api_key()
        _AI_AVAILABLE = bool(key and key != "your_anthropic_api_key_here")
    return _AI_AVAILABLE


# ─── 1. Mapping explanation ──────────────────────────────────────────────────


async def explain_mapping(
    raw_tag: str,
    proposed_binding: dict,
    model_context: dict,
) -> dict:
    """
    Claude writes evidence/counter-evidence narrative for an existing
    deterministic mapping proposal. The deterministic verdict stands regardless
    of Claude's output.

    Returns:
        {
          "ai_assisted": bool,
          "ai_label": str,          # honest tri-state label for the UI
          "ai_narrative": str,      # Claude's explanation (or fallback text)
          "ai_evidence": [str],     # Claude-identified evidence items
          "ai_counter_evidence": [str],
          "model": str | None,
        }
    """
    if not _ai_available():
        return _fallback_explain(raw_tag, proposed_binding)

    try:
        return await _call_claude_explain(raw_tag, proposed_binding, model_context)
    except Exception as exc:
        result = _fallback_explain(raw_tag, proposed_binding)
        result["ai_error"] = str(exc)
        result["ai_label"] = "deterministic rule active; AI explanation error; engineer approval required"
        return result


async def _call_claude_explain(
    raw_tag: str,
    proposed_binding: dict,
    model_context: dict,
) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=_api_key())

    equipment_label = model_context.get("equipment_label", "unknown equipment")
    canonical_tag = proposed_binding.get("proposed_canonical_tag", "unknown")
    asset_id = proposed_binding.get("proposed_asset_id", "unknown")
    role = proposed_binding.get("proposed_role", "unknown")
    existing_evidence = proposed_binding.get("evidence", [])
    existing_counter = proposed_binding.get("counter_evidence", [])

    prompt = (
        f"You are the ConfidenceOS HMI Compiler mapping engine.\n\n"
        f"A deterministic rule has proposed the following raw tag binding:\n"
        f"  Raw tag:        {raw_tag}\n"
        f"  Canonical tag:  {canonical_tag}\n"
        f"  Asset:          {asset_id} ({equipment_label})\n"
        f"  Signal role:    {role}\n\n"
        f"Existing deterministic evidence:\n"
        + "\n".join(f"  - {e}" for e in existing_evidence)
        + "\n\nExisting counter-evidence:\n"
        + "\n".join(f"  - {e}" for e in existing_counter)
        + "\n\n"
        f"Write a 3-5 sentence engineering explanation of why this mapping makes sense "
        f"(or why it requires caution). Then list up to 5 evidence items and up to 3 "
        f"counter-evidence items as JSON.\n\n"
        f"Respond in this JSON format exactly:\n"
        f'{{"narrative": "...", "evidence": ["...", "..."], "counter_evidence": ["..."]}}\n\n'
        f"Be concise and industrial. Do not invent tag values or system state."
    )

    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()

    parsed = _parse_json_from_response(text)
    return {
        "ai_assisted": True,
        "ai_label": "AI explanation active; deterministic rule authoritative; engineer approval required",
        "ai_narrative": parsed.get("narrative", text),
        "ai_evidence": parsed.get("evidence", []),
        "ai_counter_evidence": parsed.get("counter_evidence", []),
        "model": CLAUDE_MODEL,
    }


def _fallback_explain(raw_tag: str, proposed_binding: dict) -> dict:
    canonical = proposed_binding.get("proposed_canonical_tag", "unknown")
    role = proposed_binding.get("proposed_role", "unknown")
    narrative = (
        f"The deterministic naming rule matched '{raw_tag}' to '{canonical}' "
        f"based on prefix/suffix pattern recognition and signal role '{role}'. "
        f"No AI explanation is available — ANTHROPIC_API_KEY not configured. "
        f"Review the existing evidence and counter-evidence before approving."
    )
    return {
        "ai_assisted": False,
        "ai_label": "deterministic rule active; AI explanation unavailable (no key); engineer approval required",
        "ai_narrative": narrative,
        "ai_evidence": proposed_binding.get("evidence", []),
        "ai_counter_evidence": proposed_binding.get("counter_evidence", []),
        "model": None,
    }


# ─── 2. Arbitrary tag list parsing ──────────────────────────────────────────


async def parse_arbitrary_tags(
    raw_tag_list: list[str],
    model_context: dict,
) -> dict:
    """
    Claude proposes canonical bindings for an arbitrary pasted tag list.
    Every proposal is returned for the Mapping Court + engineer approval;
    nothing is auto-approved or auto-published.

    model_context should contain:
      - canonical_signals: list of {tag, sensor_type, role, unit, ...}
      - equipment_id, equipment_label

    Returns:
        {
          "ai_assisted": bool,
          "ai_label": str,
          "proposals": [
            {
              "raw_tag": str,
              "proposed_canonical_tag": str | None,
              "proposed_asset_id": str | None,
              "proposed_role": str | None,
              "confidence_band": str,     # HIGH / MEDIUM / LOW / UNCERTAIN
              "ai_rationale": str,
              "approval_required": True,
            }
          ],
          "model": str | None,
          "unresolved": [str],  # tags Claude couldn't map
        }
    """
    if not raw_tag_list:
        return {"ai_assisted": False, "ai_label": "no tags provided", "proposals": [], "unresolved": [], "model": None}

    if not _ai_available():
        return _fallback_parse(raw_tag_list)

    try:
        return await _call_claude_parse(raw_tag_list, model_context)
    except Exception as exc:
        result = _fallback_parse(raw_tag_list)
        result["ai_error"] = str(exc)
        result["ai_label"] = "deterministic fallback (AI error); engineer approval required for all proposals"
        return result


async def _call_claude_parse(
    raw_tag_list: list[str],
    model_context: dict,
) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=_api_key())

    signals = model_context.get("canonical_signals", [])
    equipment_label = model_context.get("equipment_label", "unknown")
    asset_id = model_context.get("equipment_id", "unknown")

    signals_text = "\n".join(
        f"  {s.get('tag')} | {s.get('sensor_type')} | role: {s.get('role')} | unit: {s.get('unit', '?')}"
        for s in signals
    )

    tags_text = "\n".join(f"  {t}" for t in raw_tag_list)

    prompt = (
        f"You are the ConfidenceOS HMI Compiler tag-mapping engine.\n\n"
        f"Active asset model: {equipment_label} (asset ID: {asset_id})\n\n"
        f"Available canonical signals in this asset model:\n{signals_text}\n\n"
        f"Raw imported tags to map:\n{tags_text}\n\n"
        f"For each raw tag, propose the best canonical binding from the list above. "
        f"Use ONLY signals from the list — do not invent new canonical tags. "
        f"If a tag cannot be confidently mapped, set proposed_canonical_tag to null.\n\n"
        f"Respond as a JSON array:\n"
        f'[\n'
        f'  {{\n'
        f'    "raw_tag": "...",\n'
        f'    "proposed_canonical_tag": "..." or null,\n'
        f'    "proposed_role": "..." or null,\n'
        f'    "confidence_band": "HIGH" | "MEDIUM" | "LOW" | "UNCERTAIN",\n'
        f'    "ai_rationale": "one sentence"\n'
        f'  }}\n'
        f']\n\n'
        f"Be conservative. Prefer UNCERTAIN over a wrong mapping. "
        f"Every proposal still requires engineer approval before publish."
    )

    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    raw_proposals = _parse_json_list_from_response(text)

    proposals = []
    unresolved = []
    for prop in raw_proposals:
        tag = prop.get("raw_tag", "")
        canonical = prop.get("proposed_canonical_tag")
        if not canonical:
            unresolved.append(tag)
        proposals.append({
            "raw_tag": tag,
            "proposed_canonical_tag": canonical,
            "proposed_asset_id": asset_id if canonical else None,
            "proposed_role": prop.get("proposed_role"),
            "confidence_band": prop.get("confidence_band", "UNCERTAIN"),
            "ai_rationale": prop.get("ai_rationale", ""),
            "approval_required": True,
            "source": "ai_parse",
        })

    # Any tags in the input but not returned by Claude go to unresolved
    returned_tags = {p.get("raw_tag") for p in raw_proposals}
    for tag in raw_tag_list:
        if tag not in returned_tags:
            unresolved.append(tag)
            proposals.append({
                "raw_tag": tag,
                "proposed_canonical_tag": None,
                "proposed_asset_id": None,
                "proposed_role": None,
                "confidence_band": "UNCERTAIN",
                "ai_rationale": "Tag not returned by AI — manual mapping required.",
                "approval_required": True,
                "source": "ai_parse_missing",
            })

    return {
        "ai_assisted": True,
        "ai_label": "AI-proposed bindings; deterministic validation pending; engineer approval required for all",
        "proposals": proposals,
        "unresolved": list(dict.fromkeys(unresolved)),
        "model": CLAUDE_MODEL,
    }


def _fallback_parse(raw_tag_list: list[str]) -> dict:
    return {
        "ai_assisted": False,
        "ai_label": "deterministic fallback; AI unavailable (no key); engineer review required for all tags",
        "proposals": [
            {
                "raw_tag": tag,
                "proposed_canonical_tag": None,
                "proposed_asset_id": None,
                "proposed_role": None,
                "confidence_band": "UNCERTAIN",
                "ai_rationale": "No AI key configured — use Manual Mapping Workflow to bind this tag.",
                "approval_required": True,
                "source": "fallback_no_key",
            }
            for tag in raw_tag_list
        ],
        "unresolved": list(raw_tag_list),
        "model": None,
    }


# ─── 3. Template suggestion ──────────────────────────────────────────────────


async def suggest_template(
    asset_description: str,
    available_templates: list[dict],
    available_signals: list[dict],
) -> dict:
    """
    Claude proposes a template assignment from the CLOSED set of real templates
    given a plain-English asset description.

    Returns:
        {
          "ai_assisted": bool,
          "ai_label": str,
          "proposed_template_id": str | None,
          "rationale": str,
          "required_roles": [str],
          "suggested_signal_map": {role: canonical_tag},
          "model": str | None,
          "approval_required": True,
        }
    """
    if not asset_description or not asset_description.strip():
        return {
            "ai_assisted": False,
            "ai_label": "no description provided",
            "proposed_template_id": None,
            "rationale": "Provide an asset description to receive a template suggestion.",
            "required_roles": [],
            "suggested_signal_map": {},
            "model": None,
            "approval_required": True,
        }

    if not _ai_available():
        return _fallback_suggest(asset_description, available_templates)

    try:
        return await _call_claude_suggest(asset_description, available_templates, available_signals)
    except Exception as exc:
        result = _fallback_suggest(asset_description, available_templates)
        result["ai_error"] = str(exc)
        result["ai_label"] = "deterministic fallback (AI error); choose template manually; engineer approval required"
        return result


async def _call_claude_suggest(
    asset_description: str,
    available_templates: list[dict],
    available_signals: list[dict],
) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=_api_key())

    template_text = "\n".join(
        f"  {t.get('template_id')} — required roles: {', '.join(t.get('required_signal_roles', []))}; "
        f"label: {t.get('label', t.get('template_id'))}"
        for t in available_templates
    )

    signals_text = "\n".join(
        f"  {s.get('tag')} | {s.get('sensor_type')} | role: {s.get('role')}"
        for s in available_signals
    )

    prompt = (
        f"You are the ConfidenceOS HMI Compiler template-suggestion engine.\n\n"
        f"An engineer has described an asset:\n  \"{asset_description}\"\n\n"
        f"Available templates (you MUST choose from this list only):\n{template_text}\n\n"
        f"Available canonical signals:\n{signals_text}\n\n"
        f"Select the most appropriate template from the list above. "
        f"Then suggest which available signal maps to each required role. "
        f"Use only signals from the list — do not invent signals.\n\n"
        f"Respond as JSON:\n"
        f'{{\n'
        f'  "proposed_template_id": "...",  // must be one of the template IDs above\n'
        f'  "rationale": "...",             // 2-3 sentence engineering explanation\n'
        f'  "required_roles": ["..."],      // roles the template requires\n'
        f'  "suggested_signal_map": {{       // role -> canonical_tag (only from the signal list)\n'
        f'    "level": "LT-5100"\n'
        f'  }}\n'
        f'}}\n\n'
        f"This is a proposal only. The compiler validates it; the engineer approves it. "
        f"Never suggest a template not in the list."
    )

    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    parsed = _parse_json_from_response(text)

    # Enforce: proposed_template_id must be a real template
    valid_ids = {t.get("template_id") for t in available_templates}
    proposed = parsed.get("proposed_template_id")
    if proposed not in valid_ids:
        proposed = None

    return {
        "ai_assisted": True,
        "ai_label": "AI proposes; compiler validates; engineer approves",
        "proposed_template_id": proposed,
        "rationale": parsed.get("rationale", ""),
        "required_roles": parsed.get("required_roles", []),
        "suggested_signal_map": parsed.get("suggested_signal_map", {}),
        "model": CLAUDE_MODEL,
        "approval_required": True,
    }


def _fallback_suggest(asset_description: str, available_templates: list[dict]) -> dict:
    template_list = [t.get("template_id") for t in available_templates]
    return {
        "ai_assisted": False,
        "ai_label": "AI unavailable (no key); choose template from dropdown; engineer approval required",
        "proposed_template_id": None,
        "rationale": (
            f"No AI key configured. Based on your description, choose from: "
            f"{', '.join(template_list)}. "
            f"Consider 'vessel' for tanks/vessels with level + flow, "
            f"'pump' for rotating equipment with vibration, "
            f"'valve' for control elements, 'flow_pair' for flow balance groups."
        ),
        "required_roles": [],
        "suggested_signal_map": {},
        "model": None,
        "approval_required": True,
    }


# ─── JSON helpers ────────────────────────────────────────────────────────────


def _parse_json_from_response(text: str) -> dict:
    """Extract a JSON object from a Claude response (handles markdown fences)."""
    # Strip ```json ... ``` fences
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    # Find first { ... }
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"narrative": text}


def _parse_json_list_from_response(text: str) -> list:
    """Extract a JSON array from a Claude response (handles markdown fences)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return []
