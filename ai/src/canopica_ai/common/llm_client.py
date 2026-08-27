"""LLM generation abstraction shared by every AI capability that calls a
generation model -- Task 2's Policy Q&A today, Tasks 3/5/6 later. Every call
site here takes an `LlmClient`, never talks to Ollama directly, which is
what let Task 9 add a second implementation (`OpenRouterTieredClient`,
`public_demo`-only) behind the same interface without touching any of them.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from canopica_ai.common.observability import record_llm_usage, traced_llm_call
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


def _record_ollama_usage(span: Any, payload: dict[str, Any], model: str) -> None:
    """Ollama reports usage under its own key names, on both `/api/generate`
    and `/api/chat`. Mapped to the OTel spec's names here, in the one place
    that can see the raw response.

    This is where the instrumentation lives rather than at each capability's
    own call site (which is what the Task 8 plan's prose said), for a
    concrete reason: `LlmResponse` deliberately carries only `text`, so a
    service-layer span has no access to token counts at all. Wrapping there
    would have meant either spans with no usage attributes, or widening
    `LlmResponse` -- and every test double of it -- purely to ferry
    telemetry through. One chokepoint covers all four capabilities instead.
    """
    record_llm_usage(
        span,
        response_model=payload.get("model", model),
        input_tokens=payload.get("prompt_eval_count", 0),
        output_tokens=payload.get("eval_count", 0),
        finish_reason=payload.get("done_reason"),
    )


class OllamaClient:
    """The `local` `inference_mode`'s `LlmClient` -- unchanged by Task 9,
    still what the authenticated app and every `ai-eval`/`e2e-ai` test
    exercise. `OpenRouterTieredClient` below is the `public_demo` one."""

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
        with traced_llm_call("chat", model=settings.ollama_generation_model) as span:
            response = httpx.post(
                f"{settings.ollama_base_url}/api/chat",
                json=body,
                timeout=settings.ollama_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            _record_ollama_usage(span, payload, settings.ollama_generation_model)
        message = payload["message"]
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
        with traced_llm_call("text_completion", model=settings.ollama_generation_model) as span:
            response = httpx.post(
                f"{settings.ollama_base_url}/api/generate",
                json=body,
                timeout=settings.ollama_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            _record_ollama_usage(span, payload, settings.ollama_generation_model)
        text: str = payload["response"]
        return LlmResponse(text=text)


class OpenRouterNotConfiguredError(RuntimeError):
    """No API key is set -- raised here rather than letting an
    unauthenticated request fail confusingly against OpenRouter's API.
    Shared with `judge_model.py`'s adapter, which imports this rather than
    keeping its own copy, since both mean exactly the same thing."""


class InferenceUnavailableError(RuntimeError):
    """Both OpenRouter tiers are rate-limited (or the paid tier's monthly
    cap is already reached), for one request. The `public_demo` app
    renders this as "temporarily unavailable" -- it is never a 500, since
    an exhausted tier is an expected, bounded outcome design doc §2.7
    accounts for, not a bug."""


_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"

# Matches judge_model.py's own `_RETRYABLE_ERROR_CODES` for the identical
# OpenRouter error shape -- 429 (rate limit), 502/503 (upstream outage,
# hit live 2026-08-26: a real "Service temporarily overloaded" 502 from
# the free-tier model), and 404 (a real transient gap this project also
# hit, per that module's own history). Design doc §2.10's "Tiered
# circuit breaker" is explicit that the fallback exists for "once both
# are exhausted **or on an upstream outage**", not only a 429.
_RETRYABLE_UPSTREAM_ERROR_CODES = frozenset({404, 429, 502, 503})


class _RetryableUpstreamError(RuntimeError):
    """Internal control-flow signal: this tier's model hit a retryable
    upstream failure (see `_RETRYABLE_UPSTREAM_ERROR_CODES`). Never
    escapes `OpenRouterTieredClient.generate` -- every path through it
    either falls back to the other tier or is re-raised as the
    caller-facing `InferenceUnavailableError` above."""


def _current_month_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _read_spend(path: Path) -> float:
    if not path.exists():
        return 0.0
    record = json.loads(path.read_text())
    if record["month"] != _current_month_key():
        return 0.0
    spent: float = record["spent_usd"]
    return spent


def _add_spend(path: Path, additional_usd: float) -> None:
    updated = _read_spend(path) + additional_usd
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"month": _current_month_key(), "spent_usd": updated}))


@contextlib.contextmanager
def _spend_lock(path: Path) -> Iterator[None]:
    """Serializes a whole cap-check-then-record section across threads and
    OS processes on the same host -- a background security review of this
    client's initial commit (f42b46c) flagged the unguarded version as
    both a lost-update race (`_add_spend`'s read-modify-write) and a
    fail-open gap (two concurrent calls could each read spend under the
    cap and both proceed to the paid model before either recorded its
    cost). An flock on a sibling lock file closes both at once, since
    every caller holds it across the whole check-call-record section, not
    just the final write.

    A cross-process file lock, not a `threading.Lock` -- `Settings`'s own
    "a file... is enough for this scale, not a metering service" already
    accepts a single-host deployment, so this matches that scope exactly:
    correct if the public demo ever runs multiple worker processes on one
    machine, silently insufficient only if it ever spans multiple
    machines, which the file-based spend store could not have supported
    either way.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


class OpenRouterTieredClient:
    """The `public_demo` `inference_mode`'s `LlmClient` (Task 9 plan, Step
    1) -- Policy Q&A's general-question path only (design doc §2.7), never
    the authenticated app. Tries the pinned free-tier model first; on a
    rate limit, falls back to the pinned paid model for that one request,
    provided this calendar month's tracked paid spend hasn't already met
    the cap; once both tiers are unavailable, raises
    `InferenceUnavailableError` rather than a raw upstream error.

    Implements only `LlmClient` (`generate`), not the tool-calling or
    structured-generation protocols -- `public_demo/app.py` only ever
    calls `policy_intelligence.qa.service.answer_general()`, which needs
    nothing else.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        if not self._settings.openrouter_api_key:
            raise OpenRouterNotConfiguredError(
                "CANOPICA_OPENROUTER_API_KEY is not set -- required for the public "
                "demo's tiered inference client (ai/.env locally, the OPENROUTER_API_KEY "
                "repo secret when deployed)"
            )

    def generate(self, prompt: str) -> LlmResponse:
        settings = self._settings
        try:
            return self._call(settings.openrouter_public_demo_free_model, prompt)
        except _RetryableUpstreamError:
            pass

        # Held across the cap check, the paid call, and the spend record --
        # see _spend_lock's docstring for the race this closes.
        with _spend_lock(settings.openrouter_public_demo_spend_file):
            if _read_spend(settings.openrouter_public_demo_spend_file) >= (
                settings.openrouter_public_demo_monthly_cap_usd
            ):
                raise InferenceUnavailableError(
                    "free tier is unavailable and this month's paid-tier spend cap "
                    f"(${settings.openrouter_public_demo_monthly_cap_usd:.2f}) is already reached"
                )

            try:
                response, cost_usd = self._call_and_cost(
                    settings.openrouter_public_demo_paid_model, prompt
                )
            except _RetryableUpstreamError as error:
                raise InferenceUnavailableError(
                    "both the free and paid OpenRouter tiers are unavailable"
                ) from error

            _add_spend(settings.openrouter_public_demo_spend_file, cost_usd)
            return response

    def _call(self, model: str, prompt: str) -> LlmResponse:
        response, _ = self._call_and_cost(model, prompt)
        return response

    def _call_and_cost(self, model: str, prompt: str) -> tuple[LlmResponse, float]:
        settings = self._settings
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        with traced_llm_call("chat", model=model, provider=_provider_for(model)) as span:
            response = httpx.post(
                _OPENROUTER_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json=body,
                timeout=settings.openrouter_timeout_seconds,
            )
            if response.status_code in _RETRYABLE_UPSTREAM_ERROR_CODES:
                raise _RetryableUpstreamError(
                    f"{model} returned a retryable upstream error: {response.status_code}"
                )
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                error = payload["error"]
                if error.get("code") in _RETRYABLE_UPSTREAM_ERROR_CODES:
                    raise _RetryableUpstreamError(
                        f"{model} returned a retryable upstream error: {error}"
                    )
                raise RuntimeError(f"OpenRouter call to {model} failed: {error}")
            usage = payload.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            record_llm_usage(
                span,
                response_model=payload.get("model", model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=payload.get("choices", [{}])[0].get("finish_reason"),
            )
        text: str = payload["choices"][0]["message"]["content"]
        cost_usd = self._cost_usd(model, input_tokens, output_tokens)
        return LlmResponse(text=text), cost_usd

    def _cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        settings = self._settings
        if model != settings.openrouter_public_demo_paid_model:
            return 0.0
        return (
            input_tokens * settings.openrouter_public_demo_paid_input_price_per_mtok_usd
            + output_tokens * settings.openrouter_public_demo_paid_output_price_per_mtok_usd
        ) / 1_000_000


def build_llm_client(settings: Settings) -> LlmClient:
    """Task 9 plan's Step 4 wiring: `answer_general()`'s default
    `llm_client` resolves from `settings.inference_mode` here instead of
    hardcoding `OllamaClient`, so `local` (the default, unchanged for
    every earlier task and every existing test) still gets `OllamaClient`,
    and `public_demo` gets this tiered client.

    `answer_denial` deliberately does not use this factory -- "why was I
    denied" stays authenticated-only regardless of `inference_mode`
    (design doc §2.7's public-surface scoping), so it keeps constructing
    `OllamaClient` directly.
    """
    if settings.inference_mode == "public_demo":
        return OpenRouterTieredClient(settings)
    return OllamaClient(settings)


def _provider_for(model: str) -> str:
    """`gen_ai.provider.name` for an OpenRouter-routed model -- derived
    from the model string's own `provider/name` shape rather than hardcoded
    per pinned model, so repointing `openrouter_public_demo_paid_model`
    (e.g. to `anthropic/claude-haiku-4.5`, docs/STATUS.md's "Public demo
    inference" row) needs no change here. Off-enum for anything other than
    `anthropic`, the one real value in `gen_ai.provider.name`'s enum this
    codebase has ever actually reached -- the spec permits a custom value
    for a provider it doesn't enumerate, same treatment as `"ollama"`."""
    return model.split("/", 1)[0]
