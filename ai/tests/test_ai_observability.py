"""AI-layer OTel instrumentation (Task 8 plan; design doc §2.8): the
`gen_ai.*` span attributes every LLM and retrieval call emits, and the
live per-request `rag_citation_grounded` signal on top of them.

Two layers, deliberately:

- The unit tests below assert the exact attribute *names* against an
  in-memory exporter, with no stack running. Names are the whole point of
  a semantic convention -- a typo'd `gen_ai.usage.input_token` is
  invisible in Jaeger (the span still renders, the attribute just never
  matches a query) and would sail past an "is there a trace" check. They
  are also the part most likely to drift: OTel's GenAI conventions are
  still Development-stability, and moved to their own repository in
  v1.42.0 (2026-06-12) while this phase was being built.
- `TestAgainstRealJaeger` at the bottom is the `e2e` counterpart, polling
  Jaeger's own query API for a real trace from a real question -- the
  same shape `data-platform/tests/test_observability.py` already
  established, not a mock.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from canopica_ai.common import observability
from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.qa.service import answer_general
from canopica_ai.policy_intelligence.retrieval import RetrievedChunk

_SpansFn = Callable[[], tuple[ReadableSpan, ...]]


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> _SpansFn:
    """Swaps the module's tracer for one exporting to memory. Patched by
    dotted path rather than attribute access because `--no-implicit-
    reexport` refuses the latter for an imported name."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("canopica_ai.test")
    monkeypatch.setattr(
        "canopica_ai.common.observability.init_tracer", lambda *args, **kwargs: tracer
    )
    return exporter.get_finished_spans


def _only(spans: tuple[ReadableSpan, ...]) -> ReadableSpan:
    assert len(spans) == 1, f"expected exactly one span, got {[s.name for s in spans]}"
    return spans[0]


def _attributes(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


class TestLlmSpans:
    def test_the_span_is_named_operation_then_model(self, spans: _SpansFn) -> None:
        """OTel's GenAI convention prescribes `{gen_ai.operation.name}
        {gen_ai.request.model}` -- not a free-form name."""
        with observability.traced_llm_call("chat", model="llama3.2:3b"):
            pass

        assert _only(spans()).name == "chat llama3.2:3b"

    def test_the_span_carries_the_gen_ai_request_attributes(self, spans: _SpansFn) -> None:
        with observability.traced_llm_call("text_completion", model="llama3.2:3b"):
            pass

        assert _attributes(_only(spans())) == {
            "gen_ai.operation.name": "text_completion",
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": "llama3.2:3b",
        }

    def test_usage_recorded_after_the_call_lands_on_the_span(self, spans: _SpansFn) -> None:
        """Token counts only exist once the response is back, so they're
        set on the yielded span rather than passed in up front."""
        with observability.traced_llm_call("text_completion", model="llama3.2:3b") as span:
            observability.record_llm_usage(
                span,
                response_model="llama3.2:3b",
                input_tokens=1791,
                output_tokens=64,
                finish_reason="stop",
            )

        attributes = _attributes(_only(spans()))
        assert attributes["gen_ai.usage.input_tokens"] == 1791
        assert attributes["gen_ai.usage.output_tokens"] == 64
        assert attributes["gen_ai.response.model"] == "llama3.2:3b"

    def test_finish_reason_is_recorded_as_a_list(self, spans: _SpansFn) -> None:
        """The spec's attribute is `finish_reasons`, plural, and typed as
        an array -- Ollama reports a single `done_reason` string, so it is
        wrapped rather than assigned straight through."""
        with observability.traced_llm_call("text_completion", model="llama3.2:3b") as span:
            observability.record_llm_usage(
                span,
                response_model="llama3.2:3b",
                input_tokens=10,
                output_tokens=2,
                finish_reason="length",
            )

        assert _attributes(_only(spans()))["gen_ai.response.finish_reasons"] == ("length",)

    def test_a_missing_finish_reason_is_omitted_rather_than_recorded_as_none(
        self, spans: _SpansFn
    ) -> None:
        """Ollama does not always return `done_reason`. An absent
        attribute is honest; `finish_reasons=[None]` would be a lie that
        also violates the attribute's own string-array type."""
        with observability.traced_llm_call("text_completion", model="llama3.2:3b") as span:
            observability.record_llm_usage(
                span,
                response_model="llama3.2:3b",
                input_tokens=10,
                output_tokens=2,
                finish_reason=None,
            )

        assert "gen_ai.response.finish_reasons" not in _attributes(_only(spans()))


class TestRetrievalSpans:
    def test_the_span_carries_the_retrieval_attributes(self, spans: _SpansFn) -> None:
        with observability.traced_retrieval_call(index="cfr-part-273", top_k=5) as span:
            span.set_attribute("canopica.retrieval.chunk_count", 5)

        span_out = _only(spans())
        assert span_out.name == "retrieval cfr-part-273"
        attributes = _attributes(span_out)
        assert attributes["gen_ai.operation.name"] == "retrieval"
        assert attributes["db.system.name"] == "opensearch"
        assert attributes["db.namespace"] == "cfr-part-273"
        assert attributes["canopica.retrieval.chunk_count"] == 5

    def test_top_k_is_recorded_under_this_project_s_own_namespace(self, spans: _SpansFn) -> None:
        """Not `gen_ai.request.top_k`: that spec attribute means the
        sampler's top-k, not how many documents a retrieval asked for.
        Squatting on a spec name with different semantics is worse than
        an obviously-custom one."""
        with observability.traced_retrieval_call(index="cfr-part-273", top_k=5):
            pass

        attributes = _attributes(_only(spans()))
        assert attributes["canopica.retrieval.top_k"] == 5
        assert "gen_ai.request.top_k" not in attributes


class _StubLlmClient:
    """Returns a fixed answer, so these tests exercise the span wiring
    rather than a live model."""

    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, prompt: str) -> LlmResponse:
        return LlmResponse(text=self._text)


def _stub_chunks(score: float = -5.0) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            cfr_section="273.9(a)",
            heading="Income eligibility standards",
            text="Households shall meet the income eligibility standards.",
            chunk_id="273.9(a)",
            score=score,
        )
    ]


@pytest.fixture
def stub_retrieval(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[RetrievedChunk]], None]:
    def _install(chunks: list[RetrievedChunk]) -> None:
        monkeypatch.setattr(
            "canopica_ai.policy_intelligence.qa.service.hybrid_search",
            lambda *args, **kwargs: chunks,
        )

    return _install


class TestCitationGroundedAttribute:
    """Design doc §2.8's live per-request signal, sharing Task 7's own
    `citation_grounded()` rather than duplicating the logic."""

    def test_a_grounded_answer_marks_its_span_grounded(
        self, spans: _SpansFn, stub_retrieval: Callable[[list[RetrievedChunk]], None]
    ) -> None:
        stub_retrieval(_stub_chunks())

        answer = answer_general(
            "What is the income eligibility test?",
            llm_client=_StubLlmClient("Under 273.9(a), households must meet income standards."),
            record_provenance=False,
        )

        assert not answer.abstained
        capability_span = _capability_span(spans())
        assert _attributes(capability_span)["rag_citation_grounded"] is True

    def test_an_abstention_marks_its_span_not_grounded(
        self, spans: _SpansFn, stub_retrieval: Callable[[list[RetrievedChunk]], None]
    ) -> None:
        """A retrieval too weak to answer from abstains before any LLM
        call -- the attribute must still be set, or the one case most
        worth alerting on would be the one with no signal."""
        stub_retrieval(_stub_chunks(score=-11.2))

        answer = answer_general(
            "What is the airspeed velocity of an unladen swallow?",
            llm_client=_StubLlmClient("irrelevant"),
            record_provenance=False,
        )

        assert answer.abstained
        capability_span = _capability_span(spans())
        assert _attributes(capability_span)["rag_citation_grounded"] is False


def _capability_span(spans: tuple[ReadableSpan, ...]) -> ReadableSpan:
    matching = [span for span in spans if span.name == "policy_qa.answer_general"]
    assert matching, f"no capability span found among {[s.name for s in spans]}"
    return matching[-1]


JAEGER_QUERY_URL = "http://localhost:16686"


def _find_trace_spans(
    service: str,
    *,
    since_micros: int,
    until: Callable[[list[dict[str, Any]]], bool],
    deadline_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """Jaeger indexes a real span a second or two after export -- poll
    rather than asserting on the first response, the same shape
    data-platform/tests/test_observability.py already uses.

    `since_micros` (Jaeger's own `start` query param, unix microseconds)
    excludes anything exported before this test called the code under
    test. Without it, a local developer re-running this suite against
    the same long-lived Jaeger container (this project's own `make up`
    workflow, not a fresh-per-job CI container) can match a stale trace
    left over from an earlier, possibly-broken run -- caught for real
    (2026-08-25) when a crashed first attempt's error span satisfied
    "some trace exists" before the real one had even been exported.

    `until` is a second, independent fix for a related timing gap found
    the same day: the outermost span (`policy_qa.answer_general`) closes,
    and is therefore exported, *last* -- strictly after its retrieval and
    generation children, since they're nested inside its `with` block.
    Returning on "any data at all" can catch a response that already
    contains the children but not yet the parent, if Jaeger's index has
    not caught up to the most recently exported span. The caller states
    what evidence it actually needs; polling continues until that's true
    or the deadline passes, not until *something* is true.
    """
    deadline = time.monotonic() + deadline_seconds
    last_spans: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{JAEGER_QUERY_URL}/api/traces",
            params={"service": service, "start": since_micros, "limit": 20},
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        last_spans = [span for trace in body["data"] for span in trace["spans"]]
        if until(last_spans):
            return last_spans
        time.sleep(1)
    names = sorted({span["operationName"] for span in last_spans})
    pytest.fail(
        f"expected evidence not found for service={service!r} within "
        f"{deadline_seconds}s; spans seen so far had operationNames: {names}"
    )


@pytest.mark.e2e
class TestAgainstRealJaeger:
    def test_a_real_question_produces_llm_and_retrieval_spans(
        self, indexed_corpus: Settings
    ) -> None:
        """The whole point of the module, verified end to end: a real
        question through the real service, against the real corpus and
        the real local model, lands spans Jaeger can actually serve."""
        since_micros = int(time.time() * 1_000_000)
        answer_general(
            "What is the earned income deduction?",
            settings=indexed_corpus,
            record_provenance=False,
        )

        spans = _find_trace_spans(
            "canopica-ai",
            since_micros=since_micros,
            until=lambda spans: any(
                span["operationName"] == "policy_qa.answer_general" for span in spans
            ),
        )
        names = {span["operationName"] for span in spans}
        assert any(name.startswith("retrieval ") for name in names), names
        assert "policy_qa.answer_general" in names, names

        generation_spans = [
            span
            for span in spans
            if any(
                tag["key"] == "gen_ai.usage.input_tokens" for tag in span.get("tags", [])
            )
        ]
        assert generation_spans, f"no span carried gen_ai.usage.input_tokens: {names}"

        capability_spans = [
            span for span in spans if span["operationName"] == "policy_qa.answer_general"
        ]
        grounded_tags = [
            tag
            for span in capability_spans
            for tag in span.get("tags", [])
            if tag["key"] == "rag_citation_grounded"
        ]
        assert grounded_tags, "no rag_citation_grounded attribute reached Jaeger"
