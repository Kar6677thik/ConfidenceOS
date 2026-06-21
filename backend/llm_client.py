"""
llm_client.py - Small server-side LLM adapter for ConfidenceOS.

Supports:
- direct Anthropic SDK via ANTHROPIC_API_KEY
- OpenAI-compatible Claude gateways via OPENAI_COMPATIBLE_* env vars

All LLM output remains advisory. Deterministic compiler/safety logic stays
authoritative.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


def _load_env_file(path: Path) -> None:
    if load_dotenv:
        load_dotenv(path)
        return
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(Path(__file__).parent / ".env")
_load_env_file(Path(__file__).parent.parent / ".env")


ANTHROPIC_DIRECT_MODEL = "claude-sonnet-4-20250514"
OPENAI_COMPATIBLE_MODEL = "anthropic/claude-haiku-4-5"
OPENAI_COMPATIBLE_BASE_URL = "https://aicredits.in/v1"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _anthropic_key() -> str:
    return _env("ANTHROPIC_API_KEY")


def _compatible_key() -> str:
    return _env("OPENAI_COMPATIBLE_API_KEY") or _env("AICREDITS_API_KEY") or _anthropic_key()


def provider() -> str:
    configured = _env("LLM_PROVIDER").lower()
    if configured in {"openai_compatible", "anthropic"}:
        return configured
    key = _anthropic_key()
    if key.startswith("sk-live-"):
        return "openai_compatible"
    return "anthropic"


def model_name() -> str:
    if provider() == "openai_compatible":
        return _env("OPENAI_COMPATIBLE_MODEL", OPENAI_COMPATIBLE_MODEL)
    return _env("ANTHROPIC_MODEL", ANTHROPIC_DIRECT_MODEL)


def is_configured() -> bool:
    key = _compatible_key() if provider() == "openai_compatible" else _anthropic_key()
    return bool(key and key != "your_anthropic_api_key_here")


async def complete_text(
    *,
    messages: list[dict[str, str]],
    system: str | None = None,
    max_tokens: int = 512,
    model: str | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Return provider, model, and text for a chat-style completion."""
    active_provider = provider()
    active_model = model or model_name()
    if not is_configured():
        raise RuntimeError("LLM provider is not configured.")
    if active_provider == "openai_compatible":
        text = await asyncio.to_thread(
            _openai_compatible_complete,
            messages,
            system,
            max_tokens,
            active_model,
            temperature,
        )
    else:
        text = await _anthropic_complete(messages, system, max_tokens, active_model, temperature)
    return {"provider": active_provider, "model": active_model, "text": text}


def _openai_compatible_complete(
    messages: list[dict[str, str]],
    system: str | None,
    max_tokens: int,
    model: str,
    temperature: float,
) -> str:
    key = _compatible_key()
    base_url = _env("OPENAI_COMPATIBLE_BASE_URL", OPENAI_COMPATIBLE_BASE_URL).rstrip("/")
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)
    body = json.dumps({
        "model": model,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI-compatible LLM error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI-compatible LLM connection error: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenAI-compatible LLM response did not include message content.") from exc


async def _anthropic_complete(
    messages: list[dict[str, str]],
    system: str | None,
    max_tokens: int,
    model: str,
    temperature: float,
) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=_anthropic_key())
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    response = await client.messages.create(**kwargs)
    return response.content[0].text if response.content else ""
