"""Three genuinely different things make Policy Q&A abstain, and until
now all three produced a byte-identical result: `abstained=True`,
`citations=[]`, the same message. Nothing recorded which.

That gap has a cost, paid for real in CI run `32811993194`'s `e2e-ai`
job: `TestAnswerDenial` failed with `assert True is False`, and the log
could not say whether retrieval had been too weak, the assembled prompt
had not fit the model's context, or the model had produced an uncited
answer twice in a row. Those have completely different remediations --
a retrieval problem, a chunking problem, and a model-variance problem --
so "it abstained" on its own is not an actionable diagnosis.

It is also a real product gap rather than only a test-diagnostics one.
An abstention is a *deliberate refusal to answer* under this project's
"an ungrounded guess is worse than no answer" rule, and a system that
refuses ought to record why it refused -- that is what makes the
behaviour auditable later rather than merely safe in the moment.

Deliberately an in-memory field on `QaAnswer` only: it needs no schema
migration, and it surfaces directly in the pytest assertion output the
moment a test like the one above fails again.
"""

from __future__ import annotations

import pytest

from canopica_ai.policy_intelligence.qa.service import AbstentionReason, QaAnswer


class TestAbstentionReasonIsRecorded:
    def test_an_answered_question_has_no_abstention_reason(self) -> None:
        """The field must not become noise on the ordinary path -- a real
        answer abstained for no reason at all."""
        answer = QaAnswer(answer="273.9(a) sets the gross income test.", citations=["273.9(a)"])

        assert answer.abstained is False
        assert answer.abstention_reason is None

    @pytest.mark.parametrize(
        "reason",
        [
            AbstentionReason.WEAK_RETRIEVAL,
            AbstentionReason.PROMPT_TOO_LONG,
            AbstentionReason.UNGROUNDED_AFTER_RETRY,
        ],
    )
    def test_each_distinct_cause_is_separately_representable(
        self, reason: AbstentionReason
    ) -> None:
        """The whole point is that the three are told apart. A single
        boolean, or one shared 'abstained' reason string, would collapse
        exactly the distinction this exists to preserve."""
        answer = QaAnswer(answer="...", citations=[], abstained=True, abstention_reason=reason)

        assert answer.abstained is True
        assert answer.abstention_reason is reason

    def test_the_reason_appears_in_the_models_repr(self) -> None:
        """Attribution has to survive into an assertion failure message,
        because that is where it will actually be read -- CI prints the
        repr of the object, not a field a human thought to log."""
        answer = QaAnswer(
            answer="...",
            citations=[],
            abstained=True,
            abstention_reason=AbstentionReason.UNGROUNDED_AFTER_RETRY,
        )

        assert "ungrounded_after_retry" in repr(answer)
