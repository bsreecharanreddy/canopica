"""Eval-suite CI gate (Task 7 plan; design doc §2.6): baseline-relative
RAGAS/DeepEval metrics against Policy Q&A's real `answer_general()`,
gated by a cheap deterministic citation pre-check first -- design doc
§2.6's "cheap, zero-noise pre-check" ordering, so a fabricated citation
fails immediately without spending a judge call on it.

    uv run python -m canopica_ai.policy_intelligence.eval.run_eval          # CI-gate subset
    uv run python -m canopica_ai.policy_intelligence.eval.run_eval --check  # CI-gate subset, gated
    uv run python -m canopica_ai.policy_intelligence.eval.run_eval --full   # every golden question

**Real costs measured, not assumed, at every step of picking this shape**:

1. The local `llama3.2:3b` judge (this repo's own generation model, reused
   as judge) was measured at ~10 minutes for two of three metrics on a
   *single* question, then crashed -- one judge generation exceeded a
   240s timeout. Replaced with `OpenRouterJudgeModel` (`judge_model.py`):
   a judge never serves user traffic, so this repo's "self-hosted, $0"
   requirement for the *generation* model under test (unchanged, still
   local) doesn't carry over to it. Measured: all three metrics for one
   question in 76s -- the judge was never actually the bottleneck.
2. A full, real, two-question run through `run()` (retrieval + local
   Ollama generation + OpenRouter judging) measured 257s/question, ~181s
   of which is local retrieval+generation -- the *real* bottleneck.
   Naively parallelizing that across questions was tried and live-tripped
   OpenSearch's own ml-commons memory circuit breaker in ~4 seconds under
   just 3 concurrent questions -- confirming this host's existing,
   previously-documented memory constraint (STATUS.md's earlier
   circuit-breaker rows) applies to concurrent *retrieval* alone, not
   just concurrent generation. Retrieval and generation therefore stay
   strictly sequential, one question at a time.
3. Judging *is* safe to parallelize -- it's a remote OpenRouter call with
   no local resource contention -- so `run()` below pipelines it:
   question N's judging is submitted to a small thread pool and runs
   concurrently with question N+1's (much slower) local generation,
   instead of adding its own ~76s serially after every question.
4. Even pipelined, ~181s/question x 20 questions is ~60 minutes -- too
   long for a per-push gate on this project's own stated wall-clock
   priorities. `_CI_GATE_QUESTIONS` below is a stratified 8-question
   subset (one or two per §2.1 coverage area: income, deductions,
   expedited processing, categorical eligibility) that keeps the
   CI-blocking `--check` run bounded. The full ~20-question
   `golden_set.yaml` stays committed and complete -- `--full` runs every
   question, for a slower, deliberate, less-frequent check.
5. Every categorical-eligibility golden question retrieves 7 CFR
   273.2(j)(1) or (j)(2)(E) -- real subsections with no further internal
   CFR structure to split on (corpus/chunk.py's own documented exception
   to its MAX_CHUNK_CHARS cap: 7,456 and 6,040 characters respectively,
   sized for the *embedding* model's window, not the generation model's).
   A few such chunks retrieved together can put the assembled prompt over
   `ollama_num_ctx`'s budget even though each one is individually a real,
   relevant retrieval -- measured live (2026-08-24) on this exact CI-gate
   subset. `qa/service.py`'s `_retrieve_and_answer` now catches that as
   an abstention rather than crashing (a real fix, not a workaround: an
   oversized retrieval is exactly the "can't reliably answer this" case
   abstention already exists for elsewhere in that function), so
   `citation_grounded_rate` on this subset is genuinely below 1.0 by
   construction -- see `baseline.json`'s own comment for the real number.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml
from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase
from pydantic import BaseModel

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.eval.judge_model import OpenRouterJudgeModel
from canopica_ai.policy_intelligence.qa.grounding import citation_grounded
from canopica_ai.policy_intelligence.qa.service import answer_general
from canopica_ai.policy_intelligence.retrieval import hybrid_search

_GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.yaml"
_BASELINE_PATH = Path(__file__).parent / "baseline.json"

# A regression below the recorded baseline by more than this many points
# (on each metric's own 0-1 scale) fails the gate -- design doc §2.6's
# "baseline-relative thresholds", exact margin left to this task. Generous
# enough to absorb ordinary judge-score noise (an LLM judge is not
# perfectly deterministic even at temperature=0) without masking a
# genuine regression.
_REGRESSION_MARGIN = 0.05

_METRIC_NAMES = ("faithfulness", "contextual_precision", "contextual_recall")

# Judging is a remote OpenRouter call with no local resource contention
# (unlike retrieval/generation -- see module docstring point 2), so a
# small thread pool is safe here. Not set higher without re-measuring:
# OpenRouter's own free-tier rate limits for this model aren't documented,
# and this value was never stress-tested past what naturally overlaps
# with one question's own ~181s generation time.
_JUDGE_CONCURRENCY = 4

# One or two questions per §2.1 coverage area (income eligibility,
# deductions, expedited processing, categorical eligibility), picked from
# the full golden_set.yaml -- see module docstring point 4 for why this
# exists at all, not the full set.
_CI_GATE_QUESTIONS = frozenset(
    {
        "What is the income eligibility test for a household with no elderly or disabled member?",
        "How is the standard deduction amount determined?",
        "What is the earned income deduction?",
        "Does the cost of heating and cooling count toward the shelter deduction?",
        "Which households are entitled to expedited SNAP service based on income?",
        "Are residents of shelters for battered women and children eligible for expedited service?",
        "Must a State agency let households applying for public assistance also apply for SNAP "
        "at the same time?",
        "Which households are categorically eligible for SNAP based on receiving PA or SSI "
        "benefits?",
    }
)


class GoldenQuestion(BaseModel):
    question: str
    expected_cfr_sections: list[str]
    expected_output: str


class MetricScores(BaseModel):
    faithfulness: float
    contextual_precision: float
    contextual_recall: float


@dataclass(frozen=True)
class _AnsweredQuestion:
    """What `_retrieve_and_answer` hands off to the (safely parallel)
    judging phase -- plain data, no further retrieval or generation
    needed to score it."""

    question: GoldenQuestion
    actual_output: str
    retrieval_context: list[str]


def load_golden_set() -> list[GoldenQuestion]:
    data = yaml.safe_load(_GOLDEN_SET_PATH.read_text())
    return [GoldenQuestion.model_validate(item) for item in data]


def _retrieve_and_answer(
    question: GoldenQuestion, *, settings: Settings
) -> _AnsweredQuestion | None:
    """Returns None if the deterministic pre-check fails -- a fabricated
    citation means this answer is not grounded at all, and no LLM-judge
    call is spent finding that out (design doc §2.6's ordering)."""
    chunks = hybrid_search(question.question, settings=settings)
    # record_provenance=False: a golden question is synthetic eval traffic,
    # not a real user's question -- see answer_general's own docstring. It
    # also keeps this gate free of a Postgres dependency the `ai-eval` CI
    # job would otherwise have to stand up (and originally didn't, which
    # is how this surfaced: a real `psycopg.OperationalError: connection
    # refused` in CI, once the run got far enough to reach the write).
    answer = answer_general(question.question, settings=settings, record_provenance=False)
    if not citation_grounded(answer.citations, [c.chunk_id for c in chunks]):
        return None
    return _AnsweredQuestion(
        question=question,
        actual_output=answer.answer,
        retrieval_context=[c.text for c in chunks],
    )


def _judge(answered: _AnsweredQuestion, *, judge: OpenRouterJudgeModel) -> MetricScores:
    test_case = LLMTestCase(
        input=answered.question.question,
        actual_output=answered.actual_output,
        expected_output=answered.question.expected_output,
        # deepeval types this as list[str | RetrievedContextData] | None,
        # invariant against our plain list[str] -- a real chunk text list,
        # not a type mismatch in practice.
        retrieval_context=answered.retrieval_context,  # type: ignore[arg-type]
    )
    faithfulness = FaithfulnessMetric(model=judge, include_reason=False, async_mode=False)
    precision = ContextualPrecisionMetric(model=judge, include_reason=False, async_mode=False)
    recall = ContextualRecallMetric(model=judge, include_reason=False, async_mode=False)
    return MetricScores(
        faithfulness=faithfulness.measure(test_case),
        contextual_precision=precision.measure(test_case),
        contextual_recall=recall.measure(test_case),
    )


def _score_one(
    question: GoldenQuestion, *, settings: Settings, judge: OpenRouterJudgeModel
) -> MetricScores | None:
    """Single-question convenience path (used by tests): retrieval,
    generation, and judging with no pipelining. `run()` below is the real
    entry point and pipelines judging across questions instead."""
    answered = _retrieve_and_answer(question, settings=settings)
    if answered is None:
        return None
    return _judge(answered, judge=judge)


def run(
    questions: Iterable[GoldenQuestion], *, settings: Settings | None = None
) -> dict[str, float]:
    """Returns mean scores per metric, plus `citation_grounded_rate` -- the
    deterministic pre-check's own pass rate, reported alongside the
    LLM-judged metrics rather than folded into them, since it measures a
    different thing (a fabricated citation, not an unfaithful one).

    Retrieval and generation run strictly sequentially, one question at a
    time (module docstring point 2); judging for each grounded question
    is submitted to a thread pool as soon as it's ready, so it overlaps
    with the *next* question's generation instead of adding its own time
    serially after every question (module docstring point 3).
    """
    settings = settings or Settings()
    judge = OpenRouterJudgeModel(settings)
    questions = list(questions)

    grounded_count = 0
    pending: list[Future[MetricScores]] = []
    total = len(questions)
    with ThreadPoolExecutor(max_workers=_JUDGE_CONCURRENCY) as pool:
        for index, question in enumerate(questions, start=1):
            # Progress goes to stderr, unbuffered, one line per question.
            # This job is the slowest in CI by a wide margin (13-35 min) and
            # until now emitted nothing at all between start and final
            # scores, so a run that was working and a run that had hung
            # looked identical from the log -- the only way to tell them
            # apart was to open a shell on the runner and read CPU usage,
            # which is not a diagnostic anyone should need. stderr rather
            # than stdout so it never mixes into the metric lines `main()`
            # prints, which are parsed by eye against baseline.json.
            print(f"eval progress: {index}/{total} questions", file=sys.stderr, flush=True)
            answered = _retrieve_and_answer(question, settings=settings)
            if answered is None:
                continue
            grounded_count += 1
            pending.append(pool.submit(_judge, answered, judge=judge))
        print(
            f"eval progress: {total}/{total} questions answered, "
            f"awaiting {len(pending)} judge result(s)",
            file=sys.stderr,
            flush=True,
        )
        scores = [future.result() for future in pending]

    grounded_rate = grounded_count / len(questions) if questions else 0.0
    if not scores:
        return {"citation_grounded_rate": grounded_rate, **{name: 0.0 for name in _METRIC_NAMES}}
    return {
        "citation_grounded_rate": grounded_rate,
        "faithfulness": sum(s.faithfulness for s in scores) / len(scores),
        "contextual_precision": sum(s.contextual_precision for s in scores) / len(scores),
        "contextual_recall": sum(s.contextual_recall for s in scores) / len(scores),
    }


def check_against_baseline(results: dict[str, float]) -> bool:
    """True if every metric in `_METRIC_NAMES` is within `_REGRESSION_MARGIN`
    of `baseline.json`'s recorded value. `baseline.json` is a committed,
    human-reviewed artifact -- never written by this function, so a
    regression can never quietly reset its own floor."""
    baseline = json.loads(_BASELINE_PATH.read_text())
    ok = True
    for metric in _METRIC_NAMES:
        floor = baseline.get(metric)
        value = results.get(metric)
        if floor is None or value is None:
            continue
        if value < floor - _REGRESSION_MARGIN:
            print(
                f"REGRESSION: {metric} = {value:.3f}, baseline {floor:.3f} "
                f"(margin {_REGRESSION_MARGIN})",
                file=sys.stderr,
            )
            ok = False
    return ok


def main() -> None:
    check_mode = "--check" in sys.argv
    full = "--full" in sys.argv
    golden_set = load_golden_set()
    questions = golden_set if full else [q for q in golden_set if q.question in _CI_GATE_QUESTIONS]

    results = run(questions)
    for metric, value in results.items():
        print(f"{metric}: {value:.3f}")

    if check_mode and not check_against_baseline(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
