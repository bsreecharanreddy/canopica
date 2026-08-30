"""The `qc_summary` queue's real handler (Phase 4 Task 4 plan): reads a
message, delegates summarization to `canopica_ai.qc_assistant.service.
summarize` -- the sole interface into that capability, per its own module
docstring -- and writes the result back onto the `payment_error_review`
row's own `ai_summary` column, appending a `QC_DISCREPANCY_FLAGGED` audit
event. `QcSamplingService.sampleOne` only ever enqueues here for a nonzero
`error_amount` (Java's own comment), so every message this handler reads
names a real discrepancy.

Deliberately never catches `service.summarize`'s own exceptions -- same
reasoning `fraud_scoring_consumer`'s own module docstring gives: letting
them propagate is what makes `main.py`'s `poll_once` apply its one
retry/archive policy uniformly, whether the failure was a DB error here or
a grounding failure inside `ai/`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import psycopg
from canopica_ai.qc_assistant.service import summarize as summarize_fn

from canopica_worker.config import Settings
from canopica_worker.queue import Message

# Same convention document_intake_consumer.py's own _SYSTEM_ACTOR
# establishes: written by this consumer, keyed by AuditEventResponse.
# java's literal actorType match.
_SYSTEM_ACTOR = "SYSTEM"

SummarizeFn = Callable[..., str]


class PaymentErrorReviewNotFoundError(RuntimeError):
    """The message named a `payment_error_review_id` with no matching
    row. `QcSamplingService.sampleOne` inserts the row and enqueues in the
    same transaction (design doc §2.2's outbox guarantee), so a miss here
    is a real bug worth surfacing through the normal retry/archive path,
    same reasoning `fraud_scoring_consumer`'s own `DeterminationNotFoundError`
    already gives."""


def _fetch_review(review_id: str, *, settings: Settings) -> tuple[str, Decimal, Decimal]:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select determination_id, original_amount, reproduced_amount "
            "from payment_error_review where id = %s",
            (review_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise PaymentErrorReviewNotFoundError(f"payment_error_review {review_id} not found")
    return str(row[0]), row[1], row[2]


def _persist(review_id: str, determination_id: str, summary: str, *, settings: Settings) -> None:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "update payment_error_review set ai_summary = %s where id = %s",
            (summary, review_id),
        )
        cur.execute(
            "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
            "values ('QC_DISCREPANCY_FLAGGED', %s, 'eligibility_determination', %s, %s::jsonb)",
            (
                _SYSTEM_ACTOR,
                determination_id,
                json.dumps({"payment_error_review_id": review_id, "ai_summary": summary}),
            ),
        )
        # Both writes commit together on the `with` block's clean exit --
        # same connection-context-manager-as-transaction pattern every
        # other consumer's own _persist already uses.


def build_handler(
    *, settings: Settings | None = None, summarize_fn: SummarizeFn = summarize_fn
) -> Callable[[Message], None]:
    """`summarize_fn` is injectable so this consumer's own orchestration (read
    the review row, call the capability, write the result) can be tested
    without a live Ollama -- same reason every other consumer's own
    `build_handler` takes an injectable capability function. The real
    summarization logic has its own coverage in
    ai/tests/test_qc_assistant.py."""
    settings = settings or Settings()

    def handle(message: Message) -> None:
        review_id = message.message["payment_error_review_id"]
        determination_id, original_amount, reproduced_amount = _fetch_review(
            review_id, settings=settings
        )

        summary = summarize_fn(UUID(determination_id), original_amount, reproduced_amount)

        _persist(review_id, determination_id, summary, settings=settings)

    return handle
