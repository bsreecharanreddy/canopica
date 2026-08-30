"""Caseworker SOP Copilot (Phase 4 design doc §2.5): retrieve→generate
over the authored SOP corpus, with the same abstention discipline Policy
Q&A already establishes -- a weak corpus match returns "insufficient
information," never an improvised procedure. A wrong SOP answer is a
caseworker doing the wrong next step on a real case (design doc §2.5's
own stated failure mode), so this stays strictly advisory: it never
writes anything, and there is no write path anywhere in this module for
it to gain one (constraint 22's own SOP-mining sibling makes the same
point for a different capability).
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmClient, build_llm_client
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.sop_copilot.retrieval import SopRetrievedChunk
from canopica_ai.sop_copilot.retrieval import hybrid_search as _default_hybrid_search

RetrieveFn = Callable[..., list[SopRetrievedChunk]]

PROMPT_VERSION = "v1"

ABSTENTION_MESSAGE = "insufficient information in the SOP corpus to answer this"

# Same posture policy_qa.service's own RELEVANCE_THRESHOLD takes -- a
# stated, live-checkable cutoff against this corpus's own cross-encoder
# scores, not a guessed probability. Unmeasured against the real deployed
# reranker at implementation time (no live OpenSearch/Ollama available in
# this session) -- see test_sop_copilot.py's own note on what a live
# re-check should confirm before this is trusted in production, the same
# "stated, not yet measured" posture QcSamplingService.DEFAULT_SAMPLE_RATE
# already takes for a different constant.
RELEVANCE_THRESHOLD = -10.0


class SopAnswer(BaseModel):
    answer: str
    citations: list[str]
    abstained: bool = False


def _cited_sections(text: str, chunks: list[SopRetrievedChunk]) -> list[str]:
    """A citation counts only if its "Document -- Heading" label literally
    appears in the generated text -- same discipline `policy_qa.service.
    _cited_sections`'s own doc comment establishes, adapted to this
    corpus's own citation shape (a document + heading pair, not a single
    CFR section number)."""
    return [_citation_label(chunk) for chunk in chunks if _citation_label(chunk) in text]


def _citation_label(chunk: SopRetrievedChunk) -> str:
    return f"{chunk.document} -- {chunk.heading}"


def _labeled_context(chunks: list[SopRetrievedChunk]) -> str:
    return "\n\n".join(f"[{_citation_label(chunk)}]\n{chunk.text}" for chunk in chunks)


def _prompt(question: str, chunks: list[SopRetrievedChunk]) -> str:
    return (
        "You are answering a caseworker's question about SNAP case-processing procedure, using "
        "only the SOP text below. Cite the exact bracketed label(s) you used (e.g. "
        "[new_application -- Expedited service screening]) in your answer. If the text doesn't "
        "answer the question, say so plainly instead of guessing.\n"
        "Answer in at most three sentences. Be direct: no preamble, no restating the question.\n\n"
        f"SOP text:\n{_labeled_context(chunks)}\n\n"
        f"Question: {question}\n\nAnswer:"
    )


def ask(
    question: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    retrieve: RetrieveFn = _default_hybrid_search,
) -> SopAnswer:
    """`retrieve` is injectable for the same reason `llm_client` is --
    testing the draft/grounding/abstention logic here shouldn't need a
    live OpenSearch any more than it needs a live Ollama."""
    settings = settings or Settings()
    llm_client = llm_client or build_llm_client(settings)

    with traced_ai_operation("sop_copilot.ask"):
        chunks = retrieve(question, settings=settings)

        if not chunks or chunks[0].score < RELEVANCE_THRESHOLD:
            return SopAnswer(answer=ABSTENTION_MESSAGE, citations=[], abstained=True)

        response = llm_client.generate(_prompt(question, chunks))
        citations = _cited_sections(response.text, chunks)
        if not citations:
            # Same one-retry-before-abstaining discipline policy_qa.service's own
            # _retrieve_and_answer establishes: retrieval already proved relevant text
            # exists, so an uncited first attempt is most likely this small model's
            # instruction-following variance, not a structural miss.
            response = llm_client.generate(_prompt(question, chunks))
            citations = _cited_sections(response.text, chunks)
        if not citations:
            return SopAnswer(answer=ABSTENTION_MESSAGE, citations=[], abstained=True)

        return SopAnswer(answer=response.text, citations=citations, abstained=False)
