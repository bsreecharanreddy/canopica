"""OpenTelemetry span instrumentation for the worker process (design doc
§2.7, Task 8): a plain span around each `pgmq.read`/`delete`/`archive`
cycle, with the queue name and message age as attributes. Exported to the
same Jaeger the API, the data pipeline, and `ai/` already export to -- no
new tool.

The `gen_ai.*` spans Task 8's own file list also asks for (around each
classify/draft LLM call) need no code here: `document_intake_consumer.py`
and `correspondence_consumer.py` call `canopica_ai.document_intake.
service.classify_and_extract`/`canopica_ai.correspondence.service.draft`
directly, in-process (this package's own `pyproject.toml` docstring), and
both already wrap their own LLM calls in `canopica_ai.common.
observability.traced_ai_operation`/`traced_llm_call` -- those spans exist
today, exported under the `canopica-ai` service name, regardless of
whether the caller is `worker/` or `ai/` itself.

Deliberately mirrors `canopica_ai.common.observability`'s shape
(`SimpleSpanProcessor`, OTLP/HTTP, `lru_cache`d idempotent init,
`NoOpTracer` fallback) rather than importing it: `worker/` already takes
`canopica-ai` as an in-process path dependency for its consumer logic, but
reusing its *tracer* would register a second `TracerProvider` under the
`canopica-ai` service name for spans that are actually the worker's own --
a separate module, one line different (the service name passed to
`Resource.create`), is clearer than a shared one with a parameter to
switch identities.

**One real difference from `ai/`'s own module, found live, not by
inspection**: this tracer is fetched via `provider.get_tracer(...)`
directly, never `trace.set_tracer_provider(provider)` +
`trace.get_tracer(...)`. OTel's process-wide global provider can only ever
be set once; `document_intake_consumer.py`/`correspondence_consumer.py`
call straight into `canopica_ai`'s own `classify_and_extract`/`draft` in
the same process (this package's own path-dependency precedent), and that
code calls `canopica_ai.common.observability.init_tracer()` too. Confirmed
live: with both modules calling `trace.set_tracer_provider`, the second
call (whichever ran second) was silently refused ("Overriding of current
TracerProvider is not allowed"), and every `gen_ai.*` span from `ai/`'s
own LLM calls -- made *inside* a worker-triggered `poll_once` cycle --
came out tagged `service.name=canopica-worker` instead of `canopica-ai`.
Binding this tracer to its own `provider` object directly sidesteps the
global slot entirely, so this module's spans and `ai/`'s stay correctly
attributed regardless of which one happens to initialize first.
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

from canopica_worker.config import Settings


@lru_cache(maxsize=1)
def _registered_tracer(otel_exporter_endpoint: str) -> trace.Tracer:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "canopica-worker"}))
    exporter = OTLPSpanExporter(endpoint=otel_exporter_endpoint, timeout=5)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # `provider.get_tracer(...)`, not `trace.set_tracer_provider` +
    # `trace.get_tracer(...)` -- see the module docstring for why the
    # global registration is actively wrong in this specific process.
    return provider.get_tracer("canopica_worker")


def init_tracer(settings: Settings | None = None) -> trace.Tracer:
    """Registers the process-wide `TracerProvider` on first call; later
    calls return the tracer already registered. Returns a real no-op
    tracer when `settings.otel_enabled` is False, same reason `ai/`'s own
    `init_tracer` does -- an environment with no Jaeger to receive spans
    would otherwise block on a failed export retry after every cycle."""
    resolved_settings = settings or Settings()
    if not resolved_settings.otel_enabled:
        return trace.NoOpTracer()
    return _registered_tracer(resolved_settings.otel_exporter_endpoint)


@contextmanager
def traced_queue_cycle(
    queue_name: str, *, message_age_seconds: float, settings: Settings | None = None
) -> Iterator[Span]:
    """One message's read-through-delete/archive cycle (`main.poll_once`'s
    own body, from the moment a message is actually found onward -- the
    empty-queue case opens no span, since there is no message to report an
    age for). `canopica.queue.*` rather than the `messaging.*` semantic
    conventions: this project's practice (`ai/`'s own `canopica.retrieval.
    top_k`) is a custom namespace for an attribute the spec doesn't cover
    for this shape of call, and message age in particular has no spec
    equivalent."""
    with init_tracer(settings).start_as_current_span(f"pgmq {queue_name}") as span:
        span.set_attribute("canopica.queue.name", queue_name)
        span.set_attribute("canopica.queue.message_age_seconds", message_age_seconds)
        yield span
