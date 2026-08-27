"""Eval-suite CI gate (Task 7 plan; design doc §2.6). The deterministic
citation pre-check is tested here with no infra and no judge calls at
all -- proving the gate actually gates (a fabricated citation short-
circuits before any DeepEval metric runs, and thus before any of the
many-second-per-question judge cost documented in run_eval.py's own
module docstring is spent) is what Step 5 of the plan calls for. Whether
`run_eval.py --check` passes clean against the real, unmodified system is
proven for real by the CI job itself (Step 4) running it on every push,
not re-proven here as a second, ~25-minute pytest test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.eval import run_eval
from canopica_ai.policy_intelligence.eval.run_eval import GoldenQuestion
from canopica_ai.policy_intelligence.qa.service import QaAnswer
from canopica_ai.policy_intelligence.retrieval import RetrievedChunk

_QUESTION = GoldenQuestion(
    question="What is the earned income deduction?",
    expected_cfr_sections=["273.9(d)(2)"],
    expected_output="Twenty percent of gross earned income.",
)


def _chunk(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(cfr_section=chunk_id, heading="h", text="t", chunk_id=chunk_id, score=1.0)


@pytest.fixture(autouse=True)
def _stub_retrieval(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        run_eval, "hybrid_search", lambda *args, **kwargs: [_chunk("273.9(d)(2)")]
    )
    yield


class TestDeterministicPreCheckGatesBeforeAnyJudgeCall:
    def test_a_fabricated_citation_short_circuits_before_scoring(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            run_eval,
            "answer_general",
            lambda *args, **kwargs: QaAnswer(
                answer="fabricated", citations=["999.99(z)"], abstained=False
            ),
        )

        # judge=None: if the gate didn't short-circuit, constructing a
        # DeepEval metric with model=None would itself raise -- so a
        # result of None here proves the pre-check ran and stopped things
        # before any metric (and thus any judge call) was ever reached.
        result = run_eval._score_one(_QUESTION, settings=Settings(), judge=None)  # type: ignore[arg-type]

        assert result is None

    def test_an_abstained_answer_also_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An abstention has no citations at all -- citation_grounded
        # treats that the same as a fabricated one (not proven grounded),
        # so this is a second real path into the same short-circuit.
        monkeypatch.setattr(
            run_eval,
            "answer_general",
            lambda *args, **kwargs: QaAnswer(
                answer="insufficient information", citations=[], abstained=True
            ),
        )

        result = run_eval._score_one(_QUESTION, settings=Settings(), judge=None)  # type: ignore[arg-type]

        assert result is None


class TestCheckAgainstBaseline:
    """`check_against_baseline` is pure comparison logic against a
    committed file -- tested directly, no retrieval/generation/judge
    involved at all."""

    _BASELINE_JSON = (
        '{"faithfulness": 0.9, "contextual_precision": 0.9, "contextual_recall": 0.9}'
    )

    def test_a_result_within_the_margin_of_baseline_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(self._BASELINE_JSON)
        monkeypatch.setattr(run_eval, "_BASELINE_PATH", baseline_path)

        results = {"faithfulness": 0.87, "contextual_precision": 0.9, "contextual_recall": 0.95}

        assert run_eval.check_against_baseline(results) is True

    def test_a_result_below_the_margin_of_baseline_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(self._BASELINE_JSON)
        monkeypatch.setattr(run_eval, "_BASELINE_PATH", baseline_path)

        results = {"faithfulness": 0.80, "contextual_precision": 0.9, "contextual_recall": 0.9}

        assert run_eval.check_against_baseline(results) is False


class _OneShotMetric:
    """Fakes a DeepEval metric instance: `.measure()` always returns the
    one score it was built with, regardless of the `test_case` passed in."""

    def __init__(self, score: float) -> None:
        self._score = score

    def measure(self, test_case: object) -> float:
        return self._score


class _SequentialScoreMetric:
    """Fakes a DeepEval metric *class* whose successive constructions hand
    out the next score from a fixed sequence, cycling if exhausted -- lets
    a test prove `_judge` builds several fresh instances (one per repeat)
    and averages their scores, rather than judging once and trusting it."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self._next = 0

    def __call__(self, *, model: object, include_reason: bool, async_mode: bool) -> _OneShotMetric:
        score = self._scores[self._next % len(self._scores)]
        self._next += 1
        return _OneShotMetric(score)


class TestJudgingAveragesRepeatedPassesToAbsorbJudgeNoise:
    """A real incident (2026-08-27): the same 8-question judged sample
    scored `faithfulness` 1.000 on one full run and 0.875 on the next,
    against a `_REGRESSION_MARGIN` of 0.05 -- a single question's judged
    score flipping is a 1/8 = 0.125 swing in the mean, comfortably enough
    to fail the gate on judge noise alone, not a real regression. Judging
    is cheap and parallel (a remote call, no local resource contention),
    unlike generation, so repeating *it* -- not adding more questions --
    is what run_eval.py's module docstring point 6 left as the next lever
    once judged-N alone couldn't close the gap."""

    def test_a_single_question_scores_the_mean_of_its_repeated_judge_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repeats = run_eval._JUDGE_REPEATS
        # All-but-one pass scores 1.0, one scores 0.0 -- the exact shape of
        # the real incident (one bad pass dragging an otherwise-perfect
        # question down), computed against whatever `_JUDGE_REPEATS`
        # actually is rather than a hardcoded repeat count.
        scores = [1.0] * (repeats - 1) + [0.0]
        monkeypatch.setattr(run_eval, "FaithfulnessMetric", _SequentialScoreMetric(scores))
        monkeypatch.setattr(run_eval, "ContextualPrecisionMetric", _SequentialScoreMetric([1.0]))
        monkeypatch.setattr(run_eval, "ContextualRecallMetric", _SequentialScoreMetric([1.0]))
        answered = run_eval._AnsweredQuestion(
            question=_QUESTION, actual_output="x", retrieval_context=["t"]
        )

        result = run_eval._judge(answered, judge=None)  # type: ignore[arg-type]

        assert result.faithfulness == pytest.approx((repeats - 1) / repeats)


class TestProgressReportingDuringALongRun:
    """`run()` is the slowest thing in CI (13-35 min) and used to emit
    nothing between start and final scores, so a working run and a hung one
    produced byte-identical logs. These pin the progress output, because a
    signal nothing asserts is a signal that silently stops working."""

    @staticmethod
    def _stub_answer_and_judge(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            run_eval,
            "answer_general",
            lambda *args, **kwargs: QaAnswer(
                answer="grounded", citations=["273.9(d)(2)"], abstained=False
            ),
        )
        monkeypatch.setattr(
            run_eval,
            "_judge",
            lambda answered, judge: run_eval.MetricScores(
                faithfulness=1.0, contextual_precision=1.0, contextual_recall=1.0
            ),
        )
        monkeypatch.setattr(run_eval, "OpenRouterJudgeModel", lambda settings: None)

    def test_every_question_reports_its_position_and_the_total(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._stub_answer_and_judge(monkeypatch)

        run_eval.run([_QUESTION, _QUESTION, _QUESTION], settings=Settings())

        lines = capsys.readouterr().err.splitlines()
        progress = [line for line in lines if line.startswith("eval progress")]
        # One line per question, plus the closing awaiting-judges line.
        assert "eval progress: 1/3 questions" in progress
        assert "eval progress: 2/3 questions" in progress
        assert "eval progress: 3/3 questions" in progress
        assert any("3/3 questions answered" in line for line in progress)

    def test_progress_goes_to_stderr_so_it_never_contaminates_metric_output(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._stub_answer_and_judge(monkeypatch)

        run_eval.run([_QUESTION], settings=Settings())

        captured = capsys.readouterr()
        # main() prints `metric: value` lines to stdout and those are read
        # against baseline.json by eye; progress must not appear there.
        assert "eval progress" not in captured.out
        assert "eval progress" in captured.err
