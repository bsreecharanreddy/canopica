"""QC / Payment Error Rate Assistant (Phase 4 Task 4 plan): the sole
interface the worker's `qc_summary_consumer.py` calls. Fetches both
evaluations' own trace records (the original's persisted `determination_
trace`, and the reproduction's own trace `QcSamplingService` captured onto
`payment_error_review.reproduced_trace` -- `reproduce()` itself never
persists anything, per its own Java doc comment), drafts a grounded
plain-language discrepancy summary, and returns it -- never writes
anywhere itself. Same split every other AI capability in this repo
already holds.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from canopica_ai.common.llm_client import StructuredLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.qc_assistant.draft import DiscrepancyContext, draft_summary
from canopica_ai.qc_assistant.validate import grounding_errors, known_good_amounts

# Retried whole (draft + grounding check), not just the draft -- a
# schema-valid but ungrounded summary is exactly as unusable as a
# malformed one, so both failure modes share one retry budget.
_MAX_ATTEMPTS = 2


class DeterminationNotFoundError(RuntimeError):
    """The message named a `determination_id` with no matching sampled
    row. `QcSamplingService.sampleOne` inserts `payment_error_review` and
    enqueues `qc_summary` in the same transaction (design doc §2.2's
    outbox guarantee), so a miss here is a real bug worth surfacing
    through the normal retry/archive path, same reasoning `fraud_scoring_
    consumer`'s own module docstring gives."""


class SummaryGroundingError(RuntimeError):
    """The drafted summary asserted a dollar figure that doesn't trace
    back to this case's own diff or trace records, after every retry --
    raised rather than persisting a possibly-hallucinated explanation
    (constraint 21), same posture `correspondence.draft.
    ExplanationDraftError` already establishes for a different failure
    mode."""


def _fetch_traces(
    determination_id: UUID, *, settings: Settings
) -> tuple[dict[str, Any], dict[str, Any], str]:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select t.decision_results, per.reproduced_trace, d.policy_parameter_version "
            "from determination_trace t "
            "join eligibility_determination d on d.id = t.determination_id "
            "join payment_error_review per on per.determination_id = t.determination_id "
            "where t.determination_id = %s",
            (str(determination_id),),
        )
        row = cur.fetchone()
    if row is None:
        raise DeterminationNotFoundError(
            f"determination {determination_id} has no determination_trace/payment_error_review pair"
        )
    return row[0], row[1], row[2]


def summarize(
    determination_id: UUID,
    original_amount: Decimal,
    reproduced_amount: Decimal,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    settings = settings or Settings()
    original_trace, reproduced_trace, policy_parameter_version = _fetch_traces(
        determination_id, settings=settings
    )
    context = DiscrepancyContext(
        original_amount=original_amount,
        reproduced_amount=reproduced_amount,
        error_amount=reproduced_amount - original_amount,
        original_trace=original_trace,
        reproduced_trace=reproduced_trace,
        policy_parameter_version=policy_parameter_version,
    )
    known_amounts = known_good_amounts(context)

    last_errors: list[str] = []
    with traced_ai_operation("qc_assistant.summarize"):
        for _ in range(_MAX_ATTEMPTS):
            summary = draft_summary(context, settings=settings, llm_client=llm_client)
            last_errors = grounding_errors(summary, known_amounts)
            if not last_errors:
                return summary

    raise SummaryGroundingError(
        f"drafted summary for determination {determination_id} failed grounding after "
        f"{_MAX_ATTEMPTS} attempts: {last_errors}"
    )
