"""Thin wrapper around the Anthropic Messages API.

Everything the app asks of a model goes through here so that retries, JSON
handling and the "no API key configured" path live in one place. Tests swap in
a fake via :func:`set_client`.
"""
import json
import re
import threading
import time
from typing import Iterator

from . import config

_lock = threading.Lock()
_client = None
_override = None


class LLMError(RuntimeError):
    pass


class NotConfigured(LLMError):
    pass


def set_client(client) -> None:
    """Install a client (or ``None`` to restore the real one). Used by tests."""
    global _override
    _override = client


def available() -> bool:
    return _override is not None or bool(config.HAS_API_KEY)


def client():
    if _override is not None:
        return _override
    if not config.HAS_API_KEY:
        raise NotConfigured(
            "ANTHROPIC_API_KEY is not set. Add it to the environment and restart."
        )
    global _client
    with _lock:
        if _client is None:
            import anthropic

            _client = anthropic.Anthropic()
    return _client


def _tuning(effort: str | None) -> dict:
    """Per-call knobs shared by every request shape.

    Current models reject `temperature`/`top_p`/`top_k` outright, and thinking is
    on by default — `effort` is the supported way to trade depth against latency
    and spend. Note `max_tokens` caps thinking *and* answer together, so any
    caller lowering it has to leave the model room to think first.
    """
    level = effort or config.EFFORT
    return {"output_config": {"effort": level}} if level else {}


def _retryable(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in {"RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError"}:
        return True
    status = getattr(exc, "status_code", None)
    return status in {408, 409, 429, 500, 502, 503, 504}


def _with_retries(fn, attempts: int = 3):
    delay = 1.0
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except NotConfigured:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if attempt == attempts - 1 or not _retryable(exc):
                break
            time.sleep(delay)
            delay *= 2
    raise LLMError(str(last)) from last


def complete(system: str, messages: list[dict], max_tokens: int = 4096,
             model: str | None = None, effort: str | None = None) -> str:
    """Return the concatenated text of a single non-streaming completion."""
    def call():
        return client().messages.create(
            model=model or config.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            **_tuning(effort),
        )

    response = _with_retries(call)
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


def complete_structured(system: str, messages: list[dict], tool_name: str,
                        description: str, schema: dict, max_tokens: int = 4096,
                        model: str | None = None, effort: str | None = None) -> dict:
    """Force the model to answer by calling a tool, and return its arguments.

    Using tool-use rather than "reply with JSON" means the API validates the
    shape for us, which matters when hundreds of review cells run unattended.
    """
    tool = {"name": tool_name, "description": description, "input_schema": schema}

    def call():
        return client().messages.create(
            model=model or config.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            **_tuning(effort),
        )

    response = _with_retries(call)
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input)

    # Fall back to parsing text in case a model replied without the tool call.
    text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    parsed = parse_json(text)
    if parsed is None:
        raise LLMError("Model did not return structured output.")
    return parsed


def stream(system: str, messages: list[dict], max_tokens: int = 8000,
           model: str | None = None, effort: str | None = None) -> Iterator[str]:
    """Yield text deltas from a streaming completion."""
    with client().messages.stream(
        model=model or config.MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        **_tuning(effort),
    ) as response:
        yield from response.text_stream


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str):
    """Best-effort JSON parse of a model reply, tolerating code fences."""
    if not text:
        return None
    candidate = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(candidate)
    except ValueError:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except ValueError:
            return None
    return None
