"""OpenTelemetry span instrumentation for the AI capability layer (design
doc §2.8): `gen_ai.*` semantic-convention spans around every LLM call and
every retrieval call, exported to the same Jaeger the API and the
data pipeline already export to. No new observability tool -- design doc
§2.8's explicit "same stack, more attributes".

Deliberately mirrors `canopica_data.observability.tracing`'s shape
(`SimpleSpanProcessor`, OTLP/HTTP, `lru_cache`d idempotent init) rather
than inventing a second tracing convention, for the same reason that
module gives: these are short-lived processes emitting a handful of spans
each, so there is no throughput case for batching and a real risk of a
background export thread losing buffered spans at exit. It is
reimplemented here rather than imported because `ai/` and
`data-platform/` are separate `uv` projects with no shared internal
package -- introducing one for two call sites would be the premature
abstraction CLAUDE.md's conventions warn against.

**Attribute names verified live against the current spec (2026-08-25)**,
per design doc §2.8's own standing caveat rather than taken from the
implementation plan's prose. Three things had moved since the doc was
written:

1. The GenAI conventions left the main `semantic-conventions` repository
   in v1.42.0 (2026-06-12) for `open-telemetry/semantic-conventions-genai`.
2. The finish-reason attribute is `gen_ai.response.finish_reasons` --
   plural, and typed as an *array*. The plan named the singular form.
3. `gen_ai.provider.name` is a required discriminator the plan did not
   mention, and its enum has no value for Ollama or for self-hosted
   models generally. `"ollama"` is used as a custom value, which the spec
   permits; recorded here so a future reader knows it is deliberately
   off-enum rather than a typo for a real one.

Every `gen_ai.*` attribute remains **Development** stability -- none is
stable as of this writing, exactly the caveat §2.8 flagged. The database
attributes used on retrieval spans (`db.system.name`, `db.namespace`)
*are* stable, and are the current names rather than the older `db.system`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import Span

from canopica_ai.config import Settings

# Not in `gen_ai.provider.name`'s enum, which covers hosted APIs only --
# see the module docstring. A custom value is what the spec allows for a
# provider it doesn't enumerate.
_PROVIDER_OLLAMA = "ollama"


@lru_cache(maxsize=1)
def _registered_tracer(otel_exporter_endpoint: str) -> trace.Tracer:
    """`lru_cache` keyed on the one value that can vary is what makes this
    idempotent per process without a mutable module-level global -- the
    same mechanism `canopica_data.observability.tracing` uses."""
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "canopica-ai"}))
    exporter = OTLPSpanExporter(endpoint=otel_exporter_endpoint, timeout=5)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("canopica_ai")


def init_tracer(settings: Settings | None = None) -> trace.Tracer:
    """Registers the process-wide `TracerProvider` on first call; later
    calls return the tracer already registered.

    Returns a real no-op tracer instead when `settings.otel_enabled` is
    False, rather than skipping instrumentation at each call site: every
    call site unconditionally calls `span.set_attribute(...)` on whatever
    this returns, and `NoOpTracer`'s `start_as_current_span` accepts that
    the same way a real one does, so nothing downstream has to branch on
    whether tracing happens to be on. See `Settings.otel_enabled`'s own
    docstring for why this exists: an environment with no Jaeger to
    receive spans (the `ai-eval` CI job) would otherwise block on a
    failed export retry after every single span.
    """
    resolved_settings = settings or Settings()
    if not resolved_settings.otel_enabled:
        return trace.NoOpTracer()
    return _registered_tracer(resolved_settings.otel_exporter_endpoint)


@contextmanager
def traced_ai_operation(span_name: str) -> Iterator[Span]:
    """The capability-level span -- one per user-facing AI operation
    (`policy_qa.answer_general`, `analytics_copilot.ask`, ...), parenting
    the retrieval and generation spans that operation makes.

    Its own name is this project's, not the spec's: `gen_ai.operation.
    name`'s enum describes *model* operations (chat, embeddings,
    execute_tool), and none of them describes "one grounded, cited answer
    assembled from a retrieval and a generation". Naming it after the
    capability keeps the trace readable in Jaeger and gives per-request
    attributes like `rag_citation_grounded` an honest home -- the
    grounded-ness of an answer is a property of the whole operation, not
    of the single model call inside it.
    """
    with init_tracer().start_as_current_span(span_name) as span:
        yield span


@contextmanager
def traced_llm_call(
    operation: str, *, model: str, provider: str = _PROVIDER_OLLAMA
) -> Iterator[Span]:
    """One model call. `operation` is a `gen_ai.operation.name` enum value
    (`chat`, `text_completion`, `embeddings`); the span name is the spec's
    prescribed `{operation} {model}`, not a free-form string.

    `provider` defaults to Ollama's own off-enum value, unchanged for
    every call site this module had until Task 9: `OpenRouterTieredClient`
    is the first caller that passes something else, since which provider
    actually served the request depends on which OpenRouter-routed model
    is pinned (an off-enum value like `deepseek`, or the real enum value
    `anthropic` once repointed -- see docs/STATUS.md's "Public demo
    inference" row), not on anything this module itself knows.

    Yields the span so the caller can attach what only exists once the
    response is back -- see `record_llm_usage`.
    """
    with init_tracer().start_as_current_span(f"{operation} {model}") as span:
        span.set_attribute("gen_ai.operation.name", operation)
        span.set_attribute("gen_ai.provider.name", provider)
        span.set_attribute("gen_ai.request.model", model)
        yield span


def record_llm_usage(
    span: Span,
    *,
    response_model: str,
    input_tokens: int,
    output_tokens: int,
    finish_reason: str | None,
) -> None:
    """Attaches a completed call's response metadata to its span.

    `finish_reason` is singular here because Ollama reports a single
    `done_reason`, but the spec's attribute is the plural, array-typed
    `gen_ai.response.finish_reasons` -- so it is wrapped in a list. An
    absent reason is omitted entirely rather than recorded as `[None]`,
    which would both misreport and violate the attribute's string-array
    type.
    """
    span.set_attribute("gen_ai.response.model", response_model)
    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
    if finish_reason is not None:
        span.set_attribute("gen_ai.response.finish_reasons", [finish_reason])


@contextmanager
def traced_retrieval_call(*, index: str, top_k: int) -> Iterator[Span]:
    """One hybrid search against the corpus index.

    `top_k` goes under this project's own `canopica.` namespace rather than
    `gen_ai.request.top_k`: that spec attribute means the *sampler's*
    top-k, a different thing entirely, and quietly reusing a spec name
    for different semantics is worse than an obviously-custom one.
    """
    with init_tracer().start_as_current_span(f"retrieval {index}") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("db.system.name", "opensearch")
        span.set_attribute("db.namespace", index)
        span.set_attribute("canopica.retrieval.top_k", top_k)
        yield span
