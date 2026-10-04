"""Language-model clients shared by the agents: structured answers and tool-using agent loops.

Two providers implement the same interface:

* :class:`LLM` — Claude through the Anthropic Messages API (the default);
* :class:`OpenAICompatibleLLM` — any server with the OpenAI chat-completions interface:
  NVIDIA's hosted API (Nemotron 3.5 Lightning by default), vLLM, SGLang or Ollama.

The agents only call ``structured`` and ``run_tools``, so they work with either.

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
import re
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
        # Anthropic reports input/output tokens; OpenAI-compatible servers report prompt/completion tokens.
        self.input_tokens += getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
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
                call = self._execute(by_name.get(use.name), use.name, use.input if isinstance(use.input, dict) else {})
                run.calls.append(call)
                payload = call.result if isinstance(call.result, str) else json.dumps(call.result, default=str)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": payload, "is_error": not call.ok})
            messages.append({"role": "user", "content": results})
        raise LLMError(f"the agent did not finish within {max_turns} turns")

    @staticmethod
    def _execute(tool: Tool | None, name: str, raw: dict[str, Any]) -> ToolCall:
        if tool is None:
            return ToolCall(name, raw, False, f"Unknown tool '{name}'.")
        try:
            args = tool.input_model.model_validate(raw)
        except ValidationError as exc:
            return ToolCall(name, raw, False, f"Invalid input: {exc.errors(include_url=False)}")
        try:
            return ToolCall(name, raw, True, tool.handler(args))
        except ToolRejected as exc:
            return ToolCall(name, raw, False, str(exc))


# --------------------------------------------------------------------------- OpenAI-compatible servers

_THINK = re.compile(r"<think>.*?</think>", re.S)
# Reasoning budget by effort; "low" answers without a reasoning trace.
_REASONING_BUDGET = {"low": 0, "medium": 4096, "high": 16384}


def _json_text(text: str) -> str:
    """The JSON object in a reply, without a reasoning trace or code fences around it."""
    text = _THINK.sub("", text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class OpenAICompatibleLLM(LLM):
    """The same agent interface over an OpenAI-compatible chat-completions server.

    Defaults to NVIDIA's hosted API with Nemotron 3.5 Lightning (30B MoE, 3B active).
    Structured answers use ``response_format`` with a JSON schema; tool use follows the
    chat-completions function-calling format. Reasoning is switched on for medium and high
    effort through the model's chat template (``enable_thinking``).
    """

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        super().__init__(client, model)
        settings = get_settings()
        self.provider = settings.llm_provider
        self.base_url = settings.llm_base_url

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai

            with self._lock:
                if self._client is None:
                    self._client = openai.OpenAI(base_url=self.base_url, api_key=llm_api_key() or "not-needed",
                                                 timeout=get_settings().llm_timeout_s, max_retries=2)
        return self._client

    def _complete(self, *, messages: list[dict[str, Any]], effort: str, max_tokens: int,
                  tools: list[dict[str, Any]] | None = None, response_format: dict[str, Any] | None = None) -> Any:
        import openai

        budget = _REASONING_BUDGET.get(effort, 4096)
        extra: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": budget > 0}}
        if budget and self.provider == "nvidia":
            extra["reasoning_budget"] = budget
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                                  "temperature": 0.2, "extra_body": extra}
        if tools:
            kwargs["tools"], kwargs["tool_choice"] = tools, "auto"
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = self.client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMError(f"the {self.provider} API key was rejected") from exc
        except openai.NotFoundError as exc:
            raise LLMError(f"model {self.model} is not available at {self.base_url}") from exc
        except openai.RateLimitError as exc:
            raise LLMError(f"rate limited by the {self.provider} API") from exc
        except openai.BadRequestError as exc:
            raise LLMError(f"request rejected: {exc.message}") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"{self.provider} API error {exc.status_code}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError(f"could not reach {self.base_url}") from exc
        self.usage.add(getattr(response, "usage", None))
        if not response.choices:
            raise LLMError("the server returned no answer")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMError("the answer was cut off at the token limit")
        if choice.finish_reason == "content_filter":
            raise LLMError("the model declined the request")
        return choice.message

    def structured(self, *, system: str, user: str | list[dict[str, Any]], schema: type[T], effort: str = "medium",
                   max_tokens: int = 32000) -> T:
        message = self._complete(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            effort=effort, max_tokens=max_tokens,
            response_format={"type": "json_schema",
                             "json_schema": {"name": schema.__name__, "schema": strict_schema(schema), "strict": True}})
        try:
            return schema.model_validate(json.loads(_json_text(message.content)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"the answer did not match the expected structure ({type(exc).__name__})") from exc

    def run_tools(self, *, system: str, user: str, tools: list[Tool], effort: str = "high", max_turns: int = 40,
                  max_tokens: int = 32000) -> AgentRun:
        by_name = {t.name: t for t in tools}
        definitions = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                         "parameters": strict_schema(t.input_model)}} for t in tools]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        run = AgentRun(text="")
        for turn in range(1, max_turns + 1):
            message = self._complete(messages=messages, effort=effort, max_tokens=max_tokens, tools=definitions)
            run.turns = turn
            calls = list(message.tool_calls or [])
            messages.append({"role": "assistant", "content": message.content or "", **({"tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls]} if calls else {})})
            if not calls:
                run.text = _THINK.sub("", message.content or "").strip()
                return run
            for c in calls:
                try:
                    raw = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    call = ToolCall(c.function.name, {}, False, "Arguments were not valid JSON.")
                else:
                    call = self._execute(by_name.get(c.function.name), c.function.name, raw if isinstance(raw, dict) else {})
                run.calls.append(call)
                payload = call.result if isinstance(call.result, str) else json.dumps(call.result, default=str)
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": payload if call.ok else f"Error: {payload}"})
        raise LLMError(f"the agent did not finish within {max_turns} turns")


# --------------------------------------------------------------------------- availability


# The environment variable holding each provider's key.
API_KEY_VARS = {"anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"), "nvidia": ("NVIDIA_API_KEY",),
                "openai_compatible": ("TD_LLM_API_KEY",)}


def llm_api_key() -> str | None:
    for var in API_KEY_VARS.get(get_settings().llm_provider, ()):
        if os.environ.get(var):
            return os.environ[var]
    return None


def llm_enabled() -> bool:
    """Whether the agents should use the language model."""
    mode = get_settings().llm_mode
    if mode == "off":
        return False
    if mode == "on":
        return True
    return llm_api_key() is not None


def _default_factory() -> LLM:
    return LLM() if get_settings().llm_provider == "anthropic" else OpenAICompatibleLLM()


_factory: Callable[[], LLM] = _default_factory


def get_llm() -> LLM | None:
    """A client for one pipeline stage, or ``None`` when the language model is off."""
    return _factory() if llm_enabled() else None


def set_llm_factory(factory: Callable[[], LLM] | None) -> None:
    """Replace how clients are created (tests use a scripted client)."""
    global _factory
    _factory = factory or _default_factory


def status() -> dict[str, Any]:
    settings = get_settings()
    names = {"anthropic": "Anthropic", "nvidia": "NVIDIA", "openai_compatible": "OpenAI-compatible server"}
    on = llm_enabled()
    return {"enabled": on, "mode": settings.llm_mode, "model": settings.llm_model if on else None,
            "provider": names.get(settings.llm_provider, settings.llm_provider) if on else None}
