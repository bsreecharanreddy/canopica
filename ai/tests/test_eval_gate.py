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
