"""qc_summary_consumer.py's own orchestration -- read a message, call the
summarization capability, write `ai_summary` back onto the sampled
`payment_error_review` row, append `QC_DISCREPANCY_FLAGGED`, delete the
message on success, leave it for retry on a genuine processing failure.
The capability itself (`canopica_ai.qc_assistant`'s real LLM draft +
grounding check) has its own coverage in ai/tests/test_qc_assistant.py;
this file injects a stub in its place (`build_handler`'s own
`summarize_fn` parameter) so this consumer's own wiring runs on every push
against a real Postgres, same split every other consumer test file's own
module docstring already establishes.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from canopica_worker.config import Settings
from canopica_worker.main import poll_once
from canopica_worker.qc_summary_consumer import build_handler
from canopica_worker.queue import read, send

pytestmark = pytest.mark.integration


class _Review:
    def __init__(self, review_id: UUID, determination_id: UUID) -> None:
        self.review_id = review_id
        self.determination_id = determination_id


@pytest.fixture
def review(migrated_settings: Settings) -> Iterator[_Review]:
    """The minimal person -> household -> application -> program_request
    -> policy_parameter_set -> eligibility_determination ->
    payment_error_review chain this consumer's own `_fetch_review`/
    `_persist` require -- same fixture shape `test_fraud_scoring_consumer.
    py`'s own `determination` fixture already establishes (no
    `determination_trace` row needed here: `summarize_fn` is stubbed in
    every test below, so nothing in this consumer's own path reads it --
    that query is `ai/`'s own responsibility, covered there)."""
    person_id, household_id, application_id, program_request_id = (uuid.uuid4() for _ in range(4))
    parameter_set_id, determination_id, review_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
            "values (%s, 'Sam', 'Applicant', '1990-01-01', %s, 'F')",
            (person_id, f"ssn-token-{person_id}"),
        )
        cur.execute(
            "insert into household "
            "(id, head_person_id, county, address_line1, city, state, zip_code) "
            "values (%s, %s, 'Test County', '1 Test St', 'Testville', 'TS', '00000')",
            (household_id, person_id),
        )
        cur.execute(
            "insert into application (id, household_id, submitted_at, channel) "
            "values (%s, %s, now(), 'ONLINE')",
            (application_id, household_id),
        )
        cur.execute(
            "insert into program_request (id, application_id, program_code, status, requested_on) "
            "values (%s, %s, 'SNAP', 'DETERMINED', %s)",
            (program_request_id, application_id, date.today()),
        )
        effective_from = date(2000, 1, 1) + timedelta(days=parameter_set_id.int % 3650)
        cur.execute(
            "insert into policy_parameter_set "
            "(id, program_code, version_label, effective_from, source_citation, retrieved_on) "
            "values (%s, 'SNAP', %s, %s, 'test fixture', %s)",
            (parameter_set_id, f"SNAP-TEST-{parameter_set_id}", effective_from, date.today()),
        )
        cur.execute(
            "insert into eligibility_determination "
            "(id, program_request_id, benefit_month, as_of_date, eligible, benefit_amount, "
            "reason_code, policy_parameter_set_id, policy_parameter_version, decided_by) "
            "values (%s, %s, '2026-09-01', '2026-08-28', true, 649.00, 'ELIGIBLE', %s, "
            "'SNAP-TEST', 'worker.sam@canopica.local')",
            (determination_id, program_request_id, parameter_set_id),
        )
        cur.execute(
            "insert into payment_error_review "
            "(id, determination_id, original_amount, reproduced_amount, error_amount, "
            "reproduced_trace) "
            "values (%s, %s, 649.00, 683.00, 34.00, '{}'::jsonb)",
            (review_id, determination_id),
        )

    yield _Review(review_id, determination_id)


def _summarize_stub(summary: str) -> Callable[[UUID, Decimal, Decimal], str]:
    def stub(determination_id: UUID, original_amount: Decimal, reproduced_amount: Decimal) -> str:
        return summary

    return stub


def test_a_discrepancy_summary_is_persisted_and_flagged(
    migrated_settings: Settings, review: _Review
) -> None:
    queue_name = migrated_settings.qc_summary_queue
    handler = build_handler(
        settings=migrated_settings, summarize_fn=_summarize_stub("The parameter set changed.")
    )
    send(queue_name, {"payment_error_review_id": str(review.review_id)}, settings=migrated_settings)

    assert poll_once(queue_name, handler, settings=migrated_settings) is True

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select ai_summary from payment_error_review where id = %s", (review.review_id,)
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "The parameter set changed."

        cur.execute(
            "select payload->>'payment_error_review_id', payload->>'ai_summary' "
            "from audit_event where event_type = 'QC_DISCREPANCY_FLAGGED' and actor_id = 'SYSTEM' "
            "and subject_id = %s",
            (review.determination_id,),
        )
        audit_row = cur.fetchone()
        assert audit_row is not None
        assert audit_row[0] == str(review.review_id)
        assert audit_row[1] == "The parameter set changed."

    # The message was deleted on success, not left for redelivery.
    assert poll_once(queue_name, handler, settings=migrated_settings) is False


def test_a_message_naming_an_unknown_review_id_raises_not_silently_drops(
    migrated_settings: Settings,
) -> None:
    queue_name = migrated_settings.qc_summary_queue
    handler = build_handler(settings=migrated_settings, summarize_fn=_summarize_stub("unused"))
    unknown_id = str(uuid.uuid4())
    send(queue_name, {"payment_error_review_id": unknown_id}, settings=migrated_settings)

    # Below max_delivery_attempts, so the failure is swallowed by poll_once's own retry policy and
    # the message is left for redelivery rather than raised out of poll_once itself -- same
    # assertion shape test_fraud_scoring_consumer.py's own failure test uses.
    assert poll_once(queue_name, handler, settings=migrated_settings) is True
    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        # Scoped to this specific unknown id, not a global count -- migrated_settings is
        # session-scoped with no rollback between tests (same shared-state reasoning
        # QcSamplingServiceTest's own class doc comment gives on the Java side), so a global
        # count here would also see the real flag test_a_discrepancy_summary_is_persisted_and_
        # flagged already wrote.
        cur.execute(
            "select count(*) from audit_event where event_type = 'QC_DISCREPANCY_FLAGGED' "
            "and payload->>'payment_error_review_id' = %s",
            (unknown_id,),
        )
        (count,) = cur.fetchone()  # type: ignore[misc]
    assert count == 0


def test_a_summarization_failure_leaves_the_message_for_retry_not_a_silent_drop(
    migrated_settings: Settings, review: _Review
) -> None:
    retry_settings = migrated_settings.model_copy(
        update={"visibility_timeout_seconds": 1, "max_delivery_attempts": 5}
    )

    def always_fails(
        determination_id: UUID, original_amount: Decimal, reproduced_amount: Decimal
    ) -> str:
        raise RuntimeError("simulated summarization failure")

    queue_name = retry_settings.qc_summary_queue
    handler = build_handler(settings=retry_settings, summarize_fn=always_fails)
    send(queue_name, {"payment_error_review_id": str(review.review_id)}, settings=retry_settings)

    assert poll_once(queue_name, handler, settings=retry_settings) is True
    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select ai_summary from payment_error_review where id = %s", (review.review_id,)
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] is None

    time.sleep(1.5)

    message = read(queue_name, visibility_timeout_seconds=30, settings=retry_settings)
    assert message is not None
    assert message.message["payment_error_review_id"] == str(review.review_id)
    assert message.read_ct == 2
