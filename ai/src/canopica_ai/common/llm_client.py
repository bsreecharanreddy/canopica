"""LLM generation abstraction shared by every AI capability that calls a
generation model -- Task 2's Policy Q&A today, Tasks 3/5/6 later. Every call
site here takes an `LlmClient`, never talks to Ollama directly, so Task 9 can
add a second (`OpenRouterTieredClient`) implementation behind the same
interface without touching any of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from canopica_ai.config import Settings

# A pessimistic characters-per-token ratio, used to refuse a prompt that
# would not fit rather than let it be truncated. Measured (2026-08-23)
# against llama3.2:3b on this repo's own longest real prompt: 12,186
# characters evaluated as 3,105 tokens, i.e. 3.92 characters per token.
# 3.5 assumes *more* tokens than that, which is the safe direction to be
# wrong in -- it can refuse a prompt that would just barely have fitted, and
# cannot let one through that would not.
_PESSIMISTIC_CHARS_PER_TOKEN = 3.5


class PromptTooLongError(RuntimeError):
    """The prompt would not fit the model's context window.

    Raised before the request rather than detected afterwards, because
    afterwards is not detectable: Ollama truncates to fit and answers 200 OK
    with no indication that most of the prompt is gone. `prompt_eval_count`
    cannot be used to spot it either -- prompt caching legitimately lowers
    that number too, so the two cases are indistinguishable in the response.
    """


class LlmResponse(BaseModel):
    text: str


class LlmClient(Protocol):
    """Prose generation -- what a grounded, cited policy answer needs."""

    def generate(self, prompt: str) -> LlmResponse: ...


class ToolSpec(BaseModel):
    """One callable tool, in the shape Ollama's (and the wider industry's)
    `/api/chat` tool-calling accepts -- a name, a description, and a JSON
    schema for its arguments. `analytics_copilot/tools.py` builds these from
    Task 4's metric manifest; nothing here is Analytics-Copilot-specific."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    """Which tool the model picked, and with what arguments -- arguments are
    unvalidated JSON at this layer; the caller (e.g. `tools.py`'s Pydantic
    schema) is what turns a hallucinated tool name or argument into a
    rejection rather than a query against the wrong thing."""

    name: str
    arguments: dict[str, Any]


class NoToolCallError(RuntimeError):
    """The model responded without calling any tool -- e.g. it answered in
    prose instead. A caller that only knows how to run a tool call has
    nothing to do with that, so this is raised rather than returning `None`
    for the caller to forget to check."""


class ToolCallingLlmClient(Protocol):
    """Tool-selection generation -- what Task 5's Analytics Copilot needs,
    where the model's only job is picking a governed tool and its
    arguments, never writing SQL or prose. A third, narrower protocol for
    the same interface-segregation reason `StructuredLlmClient` is separate
    from `LlmClient`: a call site that only ever selects tools shouldn't
    have to accept a client that can also free-generate prose."""

    def generate_tool_call(self, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall: ...


class StructuredLlmClient(Protocol):
    """Schema-constrained generation -- what Task 3's rule-authoring copilot
    needs, where the useful output is a *shape* (a parameter diff) rather
    than prose.

    Deliberately a second, narrower protocol rather than another method on
    `LlmClient`: a call site that only composes prose shouldn't have to
    accept a client that can do more than that, and a test double for the
    prose path shouldn't have to grow a method it never calls. Interface
    segregation, and it keeps Task 2's existing stubs conforming unchanged.
    """

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse: ...


class OllamaClient:
    """The sole implementation of both protocols until Task 9's tiered
    OpenRouter-backed one lands behind the same interfaces."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def generate(self, prompt: str) -> LlmResponse:
        return self._post(prompt)

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        """Constrains decoding to `schema` via Ollama's own `format` field,
        so malformed JSON is prevented at the sampler rather than caught
        afterwards. The caller still validates the parsed result: `format`
        guarantees the *shape*, never that the values in it are sane or
        that they correspond to anything real."""
        return self._post(prompt, response_schema=schema)

    def generate_tool_call(self, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall:
        """Ollama's tool-calling mode -- a different endpoint (`/api/chat`,
        not `/api/generate`) and a different request/response envelope
        (`messages` instead of `prompt`; `message.tool_calls` instead of
        `response`), so this does not reuse `_post`."""
        self._assert_fits_context(prompt)
        settings = self._settings
        body: dict[str, Any] = {
            "model": settings.ollama_generation_model,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ],
            "stream": False,
            # Same settings-driven, measured knobs as prose/structured
            # generation -- see the class docstring above and
            # canopica_ai.config.Settings for why each one is what it is.
            "options": {
                "temperature": settings.ollama_temperature,
                "num_predict": settings.ollama_num_predict,
                "num_ctx": settings.ollama_num_ctx,
            },
            "keep_alive": settings.ollama_keep_alive,
        }
        response = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json=body,
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        message = response.json()["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise NoToolCallError(
                f"model did not call a tool; responded instead with: {message.get('content', '')!r}"
            )
        selected = tool_calls[0]["function"]
        return ToolCall(name=selected["name"], arguments=selected["arguments"])

    def _assert_fits_context(self, prompt: str) -> None:
        settings = self._settings
        estimated_tokens = len(prompt) / _PESSIMISTIC_CHARS_PER_TOKEN
        budget = settings.ollama_num_ctx - settings.ollama_num_predict
        if estimated_tokens > budget:
            raise PromptTooLongError(
                f"prompt of {len(prompt)} characters (~{estimated_tokens:.0f} tokens) "
                f"would be silently truncated: num_ctx {settings.ollama_num_ctx} minus "
                f"num_predict {settings.ollama_num_predict} leaves room for about "
                f"{budget} prompt tokens"
            )

    def _post(self, prompt: str, *, response_schema: type[BaseModel] | None = None) -> LlmResponse:
        self._assert_fits_context(prompt)
        settings = self._settings
        body: dict[str, Any] = {
            "model": settings.ollama_generation_model,
            "prompt": prompt,
            "stream": False,
            # Every value here is settings-driven and measured -- see
            # canopica_ai.config.Settings for why each one is what it is.
            "options": {
                "temperature": settings.ollama_temperature,
                "num_predict": settings.ollama_num_predict,
                "num_ctx": settings.ollama_num_ctx,
            },
            "keep_alive": settings.ollama_keep_alive,
        }
        if response_schema is not None:
            body["format"] = response_schema.model_json_schema()
        response = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json=body,
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        text: str = response.json()["response"]
        return LlmResponse(text=text)
