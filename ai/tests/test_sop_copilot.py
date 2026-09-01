"""Caseworker SOP Copilot (Phase 4 design doc §2.5). `TestAsk` below
exercises the retrieve→generate→abstain logic with an injected `retrieve`
function standing in for `hybrid_search`, the same reason every stub `llm_
client` elsewhere in this repo exists -- testing grounding/abstention
shouldn't need a live OpenSearch any more than a live Ollama. `TestCorpus`
and `TestIndexCorpus` are what actually exercise the real markdown
chunker and the real OpenSearch index against a live local stack.
"""

from __future__ import annotations

import pytest
from opensearchpy import OpenSearch

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.sop_copilot.corpus.chunk import chunk_document, load_all_chunks
from canopica_ai.sop_copilot.corpus.index import index_corpus
from canopica_ai.sop_copilot.retrieval import SopRetrievedChunk
from canopica_ai.sop_copilot.service import ABSTENTION_MESSAGE, ask


class _StubProseClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate(self, prompt: str) -> LlmResponse:
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        return LlmResponse(text=self._responses.pop(0))


def _chunk(
    document: str = "new_application",
    heading: str = "Expedited service screening",
    text: str = "Expedited cases must reach a determination within 7 days.",
    score: float = -3.0,
) -> SopRetrievedChunk:
    return SopRetrievedChunk(
        document=document, heading=heading, text=text, chunk_id=f"{document}#0", score=score
    )


class TestChunkDocument:
    """The markdown-heading splitter (chunk.py) -- structurally the only
    genuinely new parsing logic Task 7 adds; CFR's own chunker is far more
    complex because it parses irregular regulation XML, not authored
    markdown with a flat `##` structure."""

    def test_splits_on_h2_headings_and_drops_the_h1_title(self) -> None:
        markdown = (
            "# Some Document Title\n\n"
            "Intro text before any heading, not attached to any chunk.\n\n"
            "## First Section\n\nFirst section body.\n\n"
            "## Second Section\n\nSecond section body.\n"
        )
        chunks = chunk_document("some_doc", markdown)

        assert [c.heading for c in chunks] == ["First Section", "Second Section"]
        assert chunks[0].document == "some_doc"
        assert chunks[0].text == "First section body."
        assert chunks[1].text == "Second section body."

    def test_a_document_with_no_h2_headings_produces_no_chunks(self) -> None:
        assert chunk_document("empty_doc", "# Title only\n\nSome prose.\n") == []


class TestLoadAllChunks:
    """Proves the real, committed corpus files (corpus/*.md) parse
    cleanly -- no live infra needed, just the files on disk."""

    def test_the_real_corpus_produces_chunks_from_all_three_documents(self) -> None:
        chunks = load_all_chunks()

        documents = {c.document for c in chunks}
        assert documents == {"new_application", "reported_change", "renewal"}
        assert len(chunks) >= 3
        assert all(c.text for c in chunks)

    def test_readme_is_not_treated_as_a_corpus_document(self) -> None:
        chunks = load_all_chunks()
        assert "readme" not in {c.document.lower() for c in chunks}


class TestAsk:
    def test_a_weak_retrieval_abstains_without_calling_the_model(self) -> None:
        def weak_retrieve(question: str, *, settings: Settings) -> list[SopRetrievedChunk]:
            return [_chunk(score=-15.0)]

        answer = ask(
            "unrelated question",
            llm_client=_StubProseClient([]),  # would raise AssertionError if called
            retrieve=weak_retrieve,
        )

        assert answer.abstained is True
        assert answer.answer == ABSTENTION_MESSAGE
        assert answer.citations == []

    def test_a_grounded_answer_citing_the_real_label_is_returned(self) -> None:
        chunk = _chunk()

        def strong_retrieve(question: str, *, settings: Settings) -> list[SopRetrievedChunk]:
            return [chunk]

        answer = ask(
            "How fast must an expedited case be decided?",
            llm_client=_StubProseClient(
                ["Per [new_application -- Expedited service screening], within 7 days."]
            ),
            retrieve=strong_retrieve,
        )

        assert answer.abstained is False
        assert answer.citations == ["new_application -- Expedited service screening"]
        assert "7 days" in answer.answer

    def test_an_uncited_first_attempt_is_retried_once(self) -> None:
        chunk = _chunk()

        def strong_retrieve(question: str, *, settings: Settings) -> list[SopRetrievedChunk]:
            return [chunk]

        answer = ask(
            "How fast must an expedited case be decided?",
            llm_client=_StubProseClient(
                [
                    "Within 7 days.",  # no citation -- triggers the retry
                    "Per [new_application -- Expedited service screening], within 7 days.",
                ]
            ),
            retrieve=strong_retrieve,
        )

        assert answer.abstained is False
        assert answer.citations == ["new_application -- Expedited service screening"]

    def test_two_consecutive_uncited_attempts_abstain(self) -> None:
        chunk = _chunk()

        def strong_retrieve(question: str, *, settings: Settings) -> list[SopRetrievedChunk]:
            return [chunk]

        answer = ask(
            "How fast must an expedited case be decided?",
            llm_client=_StubProseClient(["Within 7 days.", "Still within 7 days, no citation."]),
            retrieve=strong_retrieve,
        )

        assert answer.abstained is True
        assert answer.answer == ABSTENTION_MESSAGE


@pytest.mark.e2e
class TestIndexAndAskAgainstARealStack:
    """The real, live-verified path: index the actual corpus into a real
    OpenSearch, then ask a real question through Ollama and confirm the
    answer cites a real chunk from the real corpus. Proves the whole
    chain -- markdown chunking, embedding, bulk indexing, hybrid search,
    generation, grounding -- works end to end, not just each piece in
    isolation. Each test indexes the corpus itself rather than relying on
    another test's own ordering -- fast enough (three small files) that
    there's no real cost to each test being independently runnable."""

    def _index(self, settings: Settings) -> None:
        client = OpenSearch(hosts=[settings.opensearch_url])
        index_corpus(client, settings)

    # `reruns=1`, same shape and same reasoning as `test_analytics_copilot.py`'s
    # `TestAskWithARealModel`: `service.py`'s own grounding retry already
    # gives this one internal second try before abstaining, so the
    # residual failure is `llama3.2:3b` failing to ground *both* tries --
    # already documented as a real, live-measured "~1-in-10" abstention-
    # variance rate for this exact test (see Phase 5 Task 1's 2026-08-30
    # `docs/STATUS.md` verification-log row, and again on 2026-08-31/09-01
    # across `33438812730`/`33451941316`), just not yet mitigated with a
    # marker until now. The sibling test below (correctly abstaining on an
    # off-topic question) stays unmarked -- retrieval failing to surface
    # anything for "capital of France" is structural, not a delicate
    # model judgment call.
    @pytest.mark.flaky(reruns=1)
    def test_a_question_matching_real_corpus_content_answers_with_a_real_citation(
        self, settings: Settings
    ) -> None:
        self._index(settings)

        answer = ask("How many days does a caseworker have to decide an expedited case?")

        assert answer.abstained is False
        assert any("Expedited service screening" in citation for citation in answer.citations)

    def test_a_question_outside_the_corpus_scope_abstains(self, settings: Settings) -> None:
        self._index(settings)

        answer = ask("What is the capital of France?")

        assert answer.abstained is True
        assert answer.answer == ABSTENTION_MESSAGE
