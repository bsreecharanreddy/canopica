"""The worker's own OTel instrumentation (design doc §2.7, Task 8): a
plain span around each `pgmq.read`/`delete`/`archive` cycle, with the
queue name and message age as attributes.

Unit tests only, against an in-memory exporter -- no live Jaeger. A real
export is instead proven by Task 8's own Step 3 live manual walkthrough
against the running local stack, the same "verified for real" bar this
project already holds Phase 1a's `docs/demo.md` and every `pytest -m e2e`
suite to; worker's own tests otherwise stay self-contained against a
Testcontainers Postgres (`tests/conftest.py`'s own docstring), and a
live-Jaeger-polling test here would be a different isolation style than
every other test in this package uses.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from canopica_worker import observability
from canopica_worker.config import Settings

_SpansFn = Callable[[], tuple[ReadableSpan, ...]]


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> _SpansFn:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("canopica_worker.test")
    monkeypatch.setattr(
        "canopica_worker.observability.init_tracer", lambda *args, **kwargs: tracer
    )
    return exporter.get_finished_spans


def _only(spans: tuple[ReadableSpan, ...]) -> ReadableSpan:
    assert len(spans) == 1, f"expected exactly one span, got {[s.name for s in spans]}"
    return spans[0]


class TestTracedQueueCycle:
    def test_the_span_is_named_after_the_queue(self, spans: _SpansFn) -> None:
        with observability.traced_queue_cycle("document_intake", message_age_seconds=1.5):
            pass

        assert _only(spans()).name == "pgmq document_intake"

    def test_the_span_carries_queue_name_and_message_age(self, spans: _SpansFn) -> None:
        with observability.traced_queue_cycle(
            "correspondence_dispatch", message_age_seconds=42.25
        ):
            pass

        attributes = dict(_only(spans()).attributes or {})
        assert attributes["canopica.queue.name"] == "correspondence_dispatch"
        assert attributes["canopica.queue.message_age_seconds"] == 42.25


class TestObservabilityCanBeDisabled:
    """Same fix, same reasoning, as `ai/`'s own `TestObservabilityCanBeDisabled`
    (`ai/tests/test_ai_observability.py`): an environment with no Jaeger
    (this project's `worker` CI job, which starts no Compose services at
    all) must not block on a doomed OTLP export retry for every queue
    cycle."""

    def test_a_disabled_tracer_is_a_real_no_op_tracer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANOPICA_OTEL_ENABLED", "false")
        monkeypatch.setenv("CANOPICA_OTEL_EXPORTER_ENDPOINT", "http://localhost:1/v1/traces")

        tracer = observability.init_tracer(Settings())

        assert isinstance(tracer, trace.NoOpTracer)

    def test_call_sites_still_run_to_completion_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANOPICA_OTEL_ENABLED", "false")
        monkeypatch.setenv("CANOPICA_OTEL_EXPORTER_ENDPOINT", "http://localhost:1/v1/traces")

        with observability.traced_queue_cycle("document_intake", message_age_seconds=0.1) as span:
            span.set_attribute("canopica.queue.name", "document_intake")
