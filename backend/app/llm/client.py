"""Claude client shared by the agents: structured answers and tool-using agent loops.

* :meth:`LLM.structured` asks for a JSON answer constrained to a Pydantic model's schema
  and validates it.
* :meth:`LLM.run_tools` runs an agent loop: the model calls the tools it is given, this
  code executes them and returns the results, until the model stops calling tools.

Requests stream (long tender documents make long requests), opt into Anthropic's
server-side fallback when a request is declined by a safety classifier, and cache the
stable system prompt. Any failure is raised as :class:`LLMError` so the calling agent
can fall back to its rule-based path.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# JSON Schema keywords the structured-output validator does not accept; descriptions are kept.
_UNSUPPORTED = {"title", "default", "examples", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                "minLength", "maxLength", "pattern", "format", "minItems", "maxItems", "uniqueItems", "multipleOf"}


class LLMError(RuntimeError):
    """The language model gave no usable answer; the caller falls back to its rules."""


class ToolRejected(Exception):
    """A tool refused the model's input (for example a price below the margin floor)."""


# --------------------------------------------------------------------------- schemas


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A Pydantic model's JSON schema in the strict form structured outputs require.

    References are inlined, every object closes ``additionalProperties`` and lists all of
    its properties as required (optional fields stay nullable), and validation keywords
    the API does not support are dropped (Pydantic re-checks them on the way back).
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            out = {k: walk(v) for k, v in node.items() if k not in _UNSUPPORTED}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(raw)


# --------------------------------------------------------------------------- tools


@dataclass
class Tool:
    """A function the model may call. Inputs are validated against ``input_model``."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], Any]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": strict_schema(self.input_model),
                "strict": True, "eager_input_streaming": True}


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    ok: bool
    result: Any


@dataclass
class AgentRun:
    text: str
    calls: list[ToolCall] = field(default_factory=list)
    turns: int = 0


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    def as_dict(self) -> dict[str, int]:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cache_read_tokens": self.cache_read_tokens}


# --------------------------------------------------------------------------- client


def _text(message: Any) -> str:
    return "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", None) == "text").strip()


class LLM:
    """Thin wrapper over the Anthropic Messages API for the pipeline agents."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.model = model or settings.llm_model
        self._client = client
        self._lock = threading.Lock()
        self.usage = Usage()

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            with self._lock:
                if self._client is None:
                    self._client = anthropic.Anthropic(timeout=get_settings().llm_timeout_s, max_retries=2)
        return self._client

    # ------------------------------------------------------------------ transport

    def _call(self, *, system: str, messages: list[dict[str, Any]], effort: str, max_tokens: int,
              tools: list[dict[str, Any]] | None = None, output_format: dict[str, Any] | None = None,
              cache_history: bool = False) -> Any:
        import anthropic

        output_config: dict[str, Any] = {"effort": effort}
        if output_format is not None:
            output_config["format"] = output_format
        kwargs: dict[str, Any] = {
            "model": self.model, "max_tokens": max_tokens, "messages": messages, "output_config": output_config,
            # The stable instructions are cached; the document and tool results follow them.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "betas": [FALLBACK_BETA], "fallbacks": "default",
        }
        if tools:
            kwargs["tools"] = tools
        if cache_history:
            # Agent loops resend the conversation each turn; caching it bills the repeat at the cache-read rate.
            kwargs["cache_control"] = {"type": "ephemeral"}
        try:
            with self.client.beta.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LLMError("the Anthropic API key was rejected") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("the API key may not use this model") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"model {self.model} is not available") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("rate limited by the Anthropic API") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"request rejected: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("could not reach the Anthropic API") from exc
        self.usage.add(getattr(message, "usage", None))
        if message.stop_reason == "refusal":
            raise LLMError("the model declined the request")
        if message.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off at the token limit")
        return message

    # ------------------------------------------------------------------ structured answers

    def structured(self, *, system: str, user: str | list[dict[str, Any]], schema: type[T], effort: str = "medium",
                   max_tokens: int = 32000) -> T:
        """Ask for one JSON answer conforming to ``schema`` and return it validated."""
        message = self._call(system=system, messages=[{"role": "user", "content": user}], effort=effort,
                             max_tokens=max_tokens,
                             output_format={"type": "json_schema", "schema": strict_schema(schema)})
        try:
            return schema.model_validate(json.loads(_text(message)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"the answer did not match the expected structure ({type(exc).__name__})") from exc

    # ------------------------------------------------------------------ agent loop

    def run_tools(self, *, system: str, user: str, tools: list[Tool], effort: str = "high", max_turns: int = 40,
                  max_tokens: int = 32000) -> AgentRun:
        """Let the model work through ``tools`` until it answers without calling one."""
        by_name = {t.name: t for t in tools}
        definitions = [t.definition() for t in tools]
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        run = AgentRun(text="")
        for turn in range(1, max_turns + 1):
            message = self._call(system=system, messages=messages, effort=effort, max_tokens=max_tokens, tools=definitions,
                                 cache_history=True)
            run.turns = turn
            # The whole assistant turn goes back unchanged (thinking blocks included).
            messages.append({"role": "assistant", "content": message.content})
            uses = [b for b in message.content if getattr(b, "type", None) == "tool_use"]
            if not uses:
                run.text = _text(message)
                return run
            results = []
            for use in uses:
                call = self._execute(by_name.get(use.name), use)
                run.calls.append(call)
                payload = call.result if isinstance(call.result, str) else json.dumps(call.result, default=str)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": payload, "is_error": not call.ok})
            messages.append({"role": "user", "content": results})
        raise LLMError(f"the agent did not finish within {max_turns} turns")

    @staticmethod
    def _execute(tool: Tool | None, use: Any) -> ToolCall:
        raw = use.input if isinstance(use.input, dict) else {}
        if tool is None:
            return ToolCall(use.name, raw, False, f"Unknown tool '{use.name}'.")
        try:
            args = tool.input_model.model_validate(raw)
        except ValidationError as exc:
            return ToolCall(use.name, raw, False, f"Invalid input: {exc.errors(include_url=False)}")
        try:
            return ToolCall(use.name, raw, True, tool.handler(args))
        except ToolRejected as exc:
            return ToolCall(use.name, raw, False, str(exc))


# --------------------------------------------------------------------------- availability


def llm_enabled() -> bool:
    """Whether the agents should use the language model."""
    mode = get_settings().llm_mode
    if mode == "off":
        return False
    if mode == "on":
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


_factory: Callable[[], LLM] = LLM


def get_llm() -> LLM | None:
    """A client for one pipeline stage, or ``None`` when the language model is off."""
    return _factory() if llm_enabled() else None


def set_llm_factory(factory: Callable[[], LLM] | None) -> None:
    """Replace how clients are created (tests use a scripted client)."""
    global _factory
    _factory = factory or LLM


def status() -> dict[str, Any]:
    settings = get_settings()
    return {"enabled": llm_enabled(), "mode": settings.llm_mode, "model": settings.llm_model if llm_enabled() else None,
            "provider": "Anthropic" if llm_enabled() else None}
