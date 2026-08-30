"""The `fraud_scoring` queue's real handler (Phase 4 Task 2 plan): reads a
message, delegates scoring to `canopica_ai.fraud_triage.service.score` --
the sole interface into that capability, per its own module docstring --
and persists a `fraud_risk_score` row for every scored case. A
`FRAUD_FLAG_RAISED` audit event is appended only when the score clears
`_REVIEW_THRESHOLD` -- a below-threshold score is still recorded (Task 3's
fairness-audit extension needs the full scored population, not only
flagged cases, to compute a selection rate), it just doesn't raise a flag.

Deliberately never catches `service.score`'s own exceptions, same
reasoning `document_intake_consumer`'s own module docstring gives: letting
them propagate is what makes `main.py`'s `poll_once` apply its one
retry/archive policy uniformly, whether the failure was a DB error here or
a scoring failure inside `ai/`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import UUID

import psycopg
from canopica_ai.fraud_triage.score import FraudScore
from canopica_ai.fraud_triage.service import score as score_fn

from canopica_worker.config import Settings
from canopica_worker.queue import Message

# Same "written by this consumer, hash chain is a DB trigger, any writer
# with insert access can append safely" reasoning `document_intake_
# consumer`'s own comment gives for _SYSTEM_ACTOR.
_SYSTEM_ACTOR = "SYSTEM"

# A starting default, not yet measured against this project's real scored
# population -- same posture `worker/config.py`'s own `visibility_timeout_
# seconds` comment takes for an unmeasured figure. Revisit once Task 3's
# review-queue UI has real flagged-case volume to size against.
_REVIEW_THRESHOLD = 0.75

ScoreFn = Callable[[UUID], FraudScore]


class DeterminationNotFoundError(RuntimeError):
    """The message named a `determination_id` with no matching row. A
    determination commits and enqueues in the same transaction (design
    doc §2.2's outbox guarantee), so a miss here is a real bug worth
    surfacing through the normal retry/archive path, not a case to
    special-case away."""


def _program_request_id(determination_id: str, cur: psycopg.Cursor) -> str:
    cur.execute(
        "select program_request_id from eligibility_determination where id = %s",
        (determination_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise DeterminationNotFoundError(f"determination {determination_id} not found")
    return str(row[0])


def _persist(determination_id: str, fraud_score: FraudScore, *, settings: Settings) -> None:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        program_request_id = _program_request_id(determination_id, cur)

        cur.execute(
            "insert into fraud_risk_score "
            "(program_request_id, determination_id, score, top_contributing_features, "
            "model_version) "
            "values (%s, %s, %s, %s::jsonb, %s)",
            (
                program_request_id,
                determination_id,
                fraud_score.score,
                json.dumps([f.model_dump() for f in fraud_score.top_contributing_features]),
                fraud_score.model_version,
            ),
        )

        if fraud_score.score >= _REVIEW_THRESHOLD:
            cur.execute(
                "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
                "values ('FRAUD_FLAG_RAISED', %s, 'eligibility_determination', %s, %s::jsonb)",
                (
                    _SYSTEM_ACTOR,
                    determination_id,
                    json.dumps(
                        {
                            "score": fraud_score.score,
                            "model_version": fraud_score.model_version,
                            "top_contributing_features": [
                                f.model_dump() for f in fraud_score.top_contributing_features
                            ],
                        }
                    ),
                ),
            )
        # Both writes (or the score-only insert, below threshold) commit
        # together on the `with` block's clean exit -- same connection-
        # context-manager-as-transaction pattern `document_intake_
        # consumer._persist` already uses.


def build_handler(
    *,
    settings: Settings | None = None,
    score_fn: ScoreFn = score_fn,
) -> Callable[[Message], None]:
    """`score_fn` is injectable so this consumer's own orchestration (call
    the capability, write the result) can be tested without a real fitted
    population -- same reasoning `document_intake_consumer.build_handler`'s
    own `classify_and_extract_fn` parameter gives. The real scoring logic
    has its own coverage in `ai/tests/test_fraud_triage.py`."""
    settings = settings or Settings()

    def handle(message: Message) -> None:
        determination_id = message.message["determination_id"]
        fraud_score = score_fn(UUID(determination_id))
        _persist(determination_id, fraud_score, settings=settings)

    return handle
