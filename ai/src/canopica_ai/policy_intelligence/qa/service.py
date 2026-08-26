"""Policy Q&A / explainability RAG (design doc §2.2): two entry points
sharing Task 1's retrieval core. A general question is answered grounded
only in retrieved text. "Why was I denied" is seeded by the applicant's own
real, persisted DMN trace merged with retrieval targeted at the specific
test that failed -- the LLM's only job is composing plain-language prose
around numbers and citations that are already correct; it never recomputes
anything, the concrete mechanism that keeps this on the "explains, never
decides" side of the governing principle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from opentelemetry import trace
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmClient, OllamaClient, PromptTooLongError
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.corpus.cfr_fetch import CFR_AS_OF_DATE
from canopica_ai.policy_intelligence.qa import provenance
from canopica_ai.policy_intelligence.qa.grounding import citation_grounded
from canopica_ai.policy_intelligence.qa.provenance import PolicyQaAnswerRecord
from canopica_ai.policy_intelligence.retrieval import RetrievedChunk, hybrid_search

# v2 (2026-08-23) added an explicit brevity constraint to both prompts.
# v3 (2026-08-23) made the denial prompt name the one citation it actually
# owes the applicant -- the section establishing the test they failed --
# after measuring v2's denial prompt citing nothing on 3 of 5 real
# generations (see _denial_prompt's own comment for the numbers).
# Bumped rather than edited in place because every recorded answer carries
# its prompt_version (design doc §2.2's reproducibility requirement) -- an
# answer generated under an earlier prompt is not reproducible from this
# one, so silently reusing the old version would make the provenance trail
# lie. Cheap to bump; a wrong provenance record is not cheap.
PROMPT_VERSION = "v3"

ABSTENTION_MESSAGE = "insufficient information in the policy corpus to answer this"

# Empirically set (2026-08-23) against the real, live index: relevant top
# hits scored roughly -4.8 to -9.6; a deliberately unrelated question
# scored -11.1 to -11.3. These are the cross-encoder's raw logits
# (unbounded, negative for a real match is normal) -- a measured cutoff
# with real margin on both sides, not a guessed probability.
RELEVANCE_THRESHOLD = -10.0

# reasonCode -> (targeted retrieval query, which decision_results keys are
# the trusted numbers worth quoting in the explanation). Vocabulary is
# exactly the rules engine's own (see rules-engine's SnapDecision tests) --
# a reasonCode outside this set only appears if the DMN model itself
# changes, at which point this mapping needs a matching update.
_DENIAL_CONTEXT: dict[str, tuple[str, tuple[str, ...]]] = {
    "GROSS_INCOME_EXCEEDS_LIMIT": (
        "gross income eligibility test for a household",
        ("Gross Income", "Gross Income Test"),
    ),
    "NET_INCOME_EXCEEDS_LIMIT": (
        "net income eligibility test for a household",
        ("Net Income", "Net Income Test"),
    ),
    # 7 CFR 273.9(d)'s deduction/allotment computation actually governs
    # this, but the corpus (design doc §2.1's own scoping) doesn't index a
    # dedicated benefit-computation section -- the best real match is
    # still 273.9(d)'s deduction text: a real citation, just an imperfect
    # one, documented here rather than hidden.
    "ZERO_BENEFIT_AMOUNT": (
        "minimum benefit amount calculation",
        ("Benefit Amount", "Computed Benefit"),
    ),
}

_DEFAULT_RETRIEVAL_QUERY = "SNAP eligibility determination"


class AbstentionReason(StrEnum):
    """Why this service declined to answer.

    Three genuinely different causes previously produced a byte-identical
    result -- `abstained=True`, no citations, the same message -- which
    made an abstention unattributable after the fact. That cost a real CI
    round trip (run `32811993194`'s `e2e-ai` job: `assert True is False`,
    with nothing in the log to say which branch fired), and the three want
    completely different responses: fix retrieval, fix chunking, or accept
    model variance.

    A `StrEnum` rather than a bare string so the set stays closed and
    each member still prints readably in an assertion failure.
    """

    WEAK_RETRIEVAL = "weak_retrieval"
    PROMPT_TOO_LONG = "prompt_too_long"
    UNGROUNDED_AFTER_RETRY = "ungrounded_after_retry"


class QaAnswer(BaseModel):
    answer: str
    citations: list[str]
    abstained: bool = False
    # In-memory only, deliberately: no schema migration, and it lands in
    # this model's own repr, which is where a failing test actually
    # surfaces it. `None` whenever `abstained` is False.
    abstention_reason: AbstentionReason | None = None


def _cited_sections(text: str, chunks: list[RetrievedChunk]) -> list[str]:
    """A citation counts only if its section identifier literally appears
    in the generated text -- not something the model self-reports in a
    separate structured field, which a small local model can't be trusted
    to always emit correctly. A hallucinated or misquoted section number
    simply matches nothing here and is silently excluded, which is exactly
    what keeps `citation_grounded` meaningful rather than vacuous: chunk_id
    and cfr_section are the same string by construction (index.py indexes
    each chunk under `_id=chunk.cfr_section`), so this list is valid input
    to both the user-facing answer and the grounding check.
    """
    return [chunk.cfr_section for chunk in chunks if chunk.cfr_section in text]


def _labeled_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{chunk.cfr_section} -- {chunk.heading}]\n{chunk.text}" for chunk in chunks
    )


@dataclass(frozen=True)
class _AnswerRequest:
    question_for_provenance: str
    retrieval_query: str
    prompt_builder: Callable[[list[RetrievedChunk]], str]
    determination_id: str | None


def _record_grounding(citations: list[str], retrieved_chunk_ids: list[str]) -> None:
    """Design doc §2.8's live, per-request grounding signal, set on
    whichever capability span is currently open -- the same
    `citation_grounded()` Task 7's CI gate calls, so the live signal and
    the gated one can never drift apart. Outside a traced operation this
    is a no-op: OTel's own non-recording span accepts and discards the
    attribute, so nothing here needs a "is tracing on" branch.
    """
    trace.get_current_span().set_attribute(
        "rag_citation_grounded", citation_grounded(citations, retrieved_chunk_ids)
    )


def _abstain(
    common_fields: dict[str, Any],
    reason: AbstentionReason,
    *,
    settings: Settings,
    record_provenance: bool,
) -> QaAnswer:
    _record_grounding([], common_fields["retrieved_chunk_ids"])
    answer = QaAnswer(
        answer=ABSTENTION_MESSAGE, citations=[], abstained=True, abstention_reason=reason
    )
    if record_provenance:
        provenance.record(
            PolicyQaAnswerRecord(
                answer=answer.answer, citations=[], abstained=True, **common_fields
            ),
            settings=settings,
        )
    return answer


def _retrieve_and_answer(
    request: _AnswerRequest,
    *,
    settings: Settings,
    llm_client: LlmClient,
    record_provenance: bool = True,
) -> QaAnswer:
    question_for_provenance = request.question_for_provenance
    determination_id = request.determination_id
    chunks = hybrid_search(request.retrieval_query, settings=settings)
    retrieval_config: dict[str, Any] = {
        "top_k": len(chunks),
        "search_pipeline": settings.cfr_search_pipeline,
    }
    common_fields: dict[str, Any] = {
        "question": question_for_provenance,
        "corpus_version": CFR_AS_OF_DATE,
        "embedding_model_version": settings.ollama_embedding_model,
        "retrieval_config": retrieval_config,
        "prompt_version": PROMPT_VERSION,
        "retrieved_chunk_ids": [c.chunk_id for c in chunks],
        "determination_id": determination_id,
    }

    if not chunks or chunks[0].score < RELEVANCE_THRESHOLD:
        return _abstain(
            common_fields,
            AbstentionReason.WEAK_RETRIEVAL,
            settings=settings,
            record_provenance=record_provenance,
        )

    try:
        response = llm_client.generate(request.prompt_builder(chunks))
    except PromptTooLongError:
        # A few individually-relevant chunks (each under the corpus's own
        # per-chunk cap -- see corpus/chunk.py's MAX_CHUNK_CHARS) can still
        # add up past the model's context budget once assembled into one
        # prompt (measured live, 2026-08-24: 273.2(j)'s 7,456-character
        # un-subdivided intro chunk alongside a few others). A retry with
        # the same chunks would hit the same, deterministic context-fit
        # check again, so there's nothing to gain from one -- this is
        # exactly the "can't reliably answer this" case abstention exists
        # for, not a crash.
        return _abstain(
            common_fields,
            AbstentionReason.PROMPT_TOO_LONG,
            settings=settings,
            record_provenance=record_provenance,
        )
    citations = _cited_sections(response.text, chunks)
    if not citations:
        # Retrieval already proved relevant text exists (checked above), so
        # an ungrounded attempt is most likely this small model's
        # non-zero-temperature instruction-following variance rather than a
        # structural miss -- observed for real (2026-08-23) on the denial
        # path: a strong 273.9(a) retrieval, but a fluent, uncited,
        # partly-fabricated explanation on the first attempt. One retry
        # recovers most of these. A second consecutive ungrounded attempt is
        # treated as a genuine grounding failure: design doc §2.2's "an
        # ungrounded guess is worse than no answer" applies just as much to
        # a citation-free generation as to a weak retrieval.
        response = llm_client.generate(request.prompt_builder(chunks))
        citations = _cited_sections(response.text, chunks)
    if not citations:
        return _abstain(
            common_fields,
            AbstentionReason.UNGROUNDED_AFTER_RETRY,
            settings=settings,
            record_provenance=record_provenance,
        )

    _record_grounding(citations, common_fields["retrieved_chunk_ids"])
    answer = QaAnswer(answer=response.text, citations=citations, abstained=False)
    if record_provenance:
        provenance.record(
            PolicyQaAnswerRecord(
                answer=answer.answer,
                citations=citations,
                abstained=False,
                generation_model=settings.ollama_generation_model,
                generation_params={},
                **common_fields,
            ),
            settings=settings,
        )
    return answer


def _general_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    return (
        "You are answering a SNAP (food assistance) policy question using "
        "only the regulation text below. Cite the exact section number(s) "
        "you used (e.g. 273.9(a)) in your answer. If the text doesn't "
        "answer the question, say so plainly instead of guessing.\n"
        "Answer in at most three sentences. Be direct: no preamble, no "
        "restating the question, no bulleted summary.\n\n"
        f"Regulation text:\n{_labeled_context(chunks)}\n\n"
        f"Question: {question}\n\nAnswer:"
    )


def answer_general(
    question: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
    record_provenance: bool = True,
) -> QaAnswer:
    """General policy question -- top-k retrieval over the CFR corpus,
    answered grounded only in retrieved text (design doc §2.2). The sole
    entry point Task 7's eval harness and Task 9's public-demo app call for
    the general-question path.

    `record_provenance=False` is for Task 7's eval harness only: a golden
    question is synthetic test traffic, not a real citizen's or worker's
    question, and `run_eval.py` grades the returned `QaAnswer`/retrieved
    chunks directly rather than reading anything back from
    `ai.policy_qa_answer` -- recording it would only commingle synthetic
    eval runs into the same audit-quality table real answers use (design
    doc §2.2's reproducibility requirement), for no benefit to either.
    Every real caller keeps the default, unchanged."""
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    request = _AnswerRequest(
        question_for_provenance=question,
        retrieval_query=question,
        prompt_builder=lambda chunks: _general_prompt(question, chunks),
        determination_id=None,
    )
    with traced_ai_operation("policy_qa.answer_general"):
        return _retrieve_and_answer(
            request, settings=settings, llm_client=llm_client, record_provenance=record_provenance
        )


def _denial_prompt(trusted_data: dict[str, Any], chunks: list[RetrievedChunk]) -> str:
    return (
        "You are explaining a SNAP (food assistance) eligibility denial to "
        "the applicant, in plain language. The numbers below are already "
        "decided and correct -- do not recompute or change them, only "
        "explain them using the regulation text that follows.\n"
        # Measured (2026-08-23, 5 real generations per variant against the
        # live index): asking only for "the section number(s) you used"
        # produced a citation on just 2 of 5 attempts -- the other 3 cited
        # nothing at all, which costs a retry and can end in a spurious
        # abstention. Naming *which* citation is required, and that it must
        # be copied from the bracketed labels, took the same question to 4
        # of 5. It is also the more correct instruction: the one thing a
        # denial explanation owes the applicant is the rule they failed.
        "You must cite the exact section number that establishes the test "
        "this household did not meet (e.g. 273.9(a)), copied exactly as it "
        "appears in brackets in the regulation text. Cite it even if you "
        "cite nothing else.\n"
        "Keep it to at most four sentences. Be direct: no preamble, no "
        "bulleted summary.\n\n"
        f"This household's determination: {trusted_data}\n\n"
        f"Regulation text:\n{_labeled_context(chunks)}\n\nExplanation:"
    )


def answer_denial(
    determination_id: str,
    bearer_token: str,
    *,
    settings: Settings | None = None,
    llm_client: LlmClient | None = None,
) -> QaAnswer:
    """"Why was I denied" -- reads the citizen's own real, persisted DMN
    trace (via the API's citizen-scoped trace endpoint, using their own
    bearer token -- this service never receives a token it can use for
    anything beyond that one read), then targets retrieval at the specific
    test that failed rather than a generic query."""
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    question_for_provenance = f"why was I denied (determination {determination_id})"

    with traced_ai_operation("policy_qa.answer_denial"):
        trace_response = httpx.get(
            f"{settings.api_url}/api/my/determinations/{determination_id}/trace",
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=30.0,
        )
        trace_response.raise_for_status()
        decision_results = trace_response.json()["decisionResults"]
        determination = decision_results["Determination"]
        reason_code = determination["reasonCode"]

        if reason_code == "ELIGIBLE":
            # Nothing to explain a denial of -- the DMN found the household
            # eligible. Deterministic from the trace alone; no LLM call, no
            # retrieval, matching the same "don't ask the model to try when the
            # answer is already known" abstention discipline used elsewhere.
            eligible_message = (
                "This determination found the household eligible, so there is no denial to explain."
            )
            # Grounded-ness is about a *cited* answer; this one is derived
            # from the trace with no retrieval at all, so it records False
            # for the same reason `citation_grounded` treats an uncited
            # answer as not-proven-grounded -- not because anything is wrong
            # with it.
            _record_grounding([], [])
            answer = QaAnswer(answer=eligible_message, citations=[], abstained=False)
            provenance.record(
                PolicyQaAnswerRecord(
                    question=question_for_provenance,
                    answer=answer.answer,
                    citations=[],
                    abstained=False,
                    corpus_version=CFR_AS_OF_DATE,
                    embedding_model_version=settings.ollama_embedding_model,
                    retrieval_config={"top_k": 0, "search_pipeline": settings.cfr_search_pipeline},
                    prompt_version=PROMPT_VERSION,
                    retrieved_chunk_ids=[],
                    determination_id=determination_id,
                ),
                settings=settings,
            )
            return answer

        retrieval_query, trusted_keys = _DENIAL_CONTEXT.get(
            reason_code, (_DEFAULT_RETRIEVAL_QUERY, ())
        )
        trusted_data: dict[str, Any] = {"reasonCode": reason_code}
        for key in trusted_keys:
            if key in decision_results:
                trusted_data[key] = decision_results[key]

        request = _AnswerRequest(
            question_for_provenance=question_for_provenance,
            retrieval_query=retrieval_query,
            prompt_builder=lambda chunks: _denial_prompt(trusted_data, chunks),
            determination_id=determination_id,
        )
        return _retrieve_and_answer(request, settings=settings, llm_client=llm_client)
