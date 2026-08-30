"""fraud_scoring_consumer.py's own orchestration -- read a message, call
the scoring capability, persist a `fraud_risk_score` row for every scored
case, append `FRAUD_FLAG_RAISED` only when the score clears the review
threshold, delete the message on success, leave it for retry on a genuine
processing failure. The capability itself (`canopica_ai.fraud_triage`'s
real feature engineering/`IsolationForest` scoring) has its own coverage
in ai/tests/test_fraud_triage.py; this file injects a stub in its place
(`build_handler`'s own `score_fn` parameter) so this consumer's own wiring
runs on every push against a real Postgres, same split test_document_
intake_consumer.py's and test_correspondence_consumer.py's own module
docstrings already establish.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from uuid import UUID

import psycopg
import pytest
from canopica_ai.fraud_triage.score import FeatureContribution, FraudScore

from canopica_worker.config import Settings
from canopica_worker.fraud_scoring_consumer import build_handler
from canopica_worker.main import poll_once
from canopica_worker.queue import read, send

pytestmark = pytest.mark.integration


class _Determination:
    def __init__(self, determination_id: UUID, program_request_id: UUID) -> None:
        self.determination_id = determination_id
        self.program_request_id = program_request_id


@pytest.fixture
def determination(migrated_settings: Settings) -> Iterator[_Determination]:
    """The minimal person -> household -> application -> program_request
    -> policy_parameter_set -> eligibility_determination chain `fraud_
    risk_score`'s own foreign keys require -- same fixture shape test_
    correspondence_consumer.py's own `determination` fixture already
    establishes (no `determination_trace` row needed here: unlike
    correspondence, nothing in this consumer's own path reads it)."""
    person_id, household_id, application_id, program_request_id = (uuid.uuid4() for _ in range(4))
    parameter_set_id, determination_id = uuid.uuid4(), uuid.uuid4()

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
        # effective_from must be unique per program_code (policy_parameter_set_unique_span) --
        # migrated_settings is session-scoped, so every test in this file shares one Postgres
        # instance and a fixed literal date collided across them, same reasoning test_
        # correspondence_consumer.py's own fixture comment gives.
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
            "values (%s, %s, '2026-09-01', '2026-08-28', true, 170.00, 'ELIGIBLE', %s, "
            "'SNAP-TEST', 'worker.sam@canopica.local')",
            (determination_id, program_request_id, parameter_set_id),
        )

    yield _Determination(determination_id, program_request_id)


def _score(value: float) -> FraudScore:
    return FraudScore(
        score=value,
        top_contributing_features=[
            FeatureContribution(feature="income_volatility", value=4.5, z_score=3.2)
        ],
        model_version="isolation-forest-v1",
    )


def test_an_above_threshold_score_is_persisted_and_raises_a_flag(
    migrated_settings: Settings, determination: _Determination
) -> None:
    fraud_score = _score(0.9)

    def stub(determination_id: UUID) -> FraudScore:
        assert determination_id == determination.determination_id
        return fraud_score

    queue_name = migrated_settings.fraud_scoring_queue
    handler = build_handler(settings=migrated_settings, score_fn=stub)
    send(
        queue_name,
        {"determination_id": str(determination.determination_id)},
        settings=migrated_settings,
    )

    assert poll_once(queue_name, handler, settings=migrated_settings) is True

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select program_request_id, score, model_version, "
            "top_contributing_features->0->>'feature' "
            "from fraud_risk_score where determination_id = %s",
            (determination.determination_id,),
        )
        row = cur.fetchone()
        assert row is not None
        program_request_id, score, model_version, top_feature = row
        assert program_request_id == determination.program_request_id
        assert float(score) == pytest.approx(0.9)
        assert model_version == "isolation-forest-v1"
        assert top_feature == "income_volatility"

        cur.execute(
            "select payload->>'score', payload->>'model_version' "
            "from audit_event where event_type = 'FRAUD_FLAG_RAISED' and actor_id = 'SYSTEM' "
            "and subject_id = %s",
            (determination.determination_id,),
        )
        audit_row = cur.fetchone()
        assert audit_row is not None
        assert float(audit_row[0]) == pytest.approx(0.9)
        assert audit_row[1] == "isolation-forest-v1"

    # The message was deleted on success, not left for redelivery.
    assert poll_once(queue_name, handler, settings=migrated_settings) is False


def test_a_below_threshold_score_is_persisted_without_raising_a_flag(
    migrated_settings: Settings, determination: _Determination
) -> None:
    fraud_score = _score(0.1)

    def stub(determination_id: UUID) -> FraudScore:
        return fraud_score

    queue_name = migrated_settings.fraud_scoring_queue
    handler = build_handler(settings=migrated_settings, score_fn=stub)
    send(
        queue_name,
        {"determination_id": str(determination.determination_id)},
        settings=migrated_settings,
    )

    assert poll_once(queue_name, handler, settings=migrated_settings) is True

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select score from fraud_risk_score where determination_id = %s",
            (determination.determination_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert float(row[0]) == pytest.approx(0.1)

        cur.execute(
            "select count(*) from audit_event where event_type = 'FRAUD_FLAG_RAISED' "
            "and subject_id = %s",
            (determination.determination_id,),
        )
        (count,) = cur.fetchone()  # type: ignore[misc]
        assert count == 0


def test_a_scoring_failure_leaves_the_message_for_retry_not_a_silent_drop(
    migrated_settings: Settings, determination: _Determination
) -> None:
    retry_settings = migrated_settings.model_copy(
        update={"visibility_timeout_seconds": 1, "max_delivery_attempts": 5}
    )

    def always_fails(determination_id: UUID) -> FraudScore:
        raise RuntimeError("simulated scoring failure")

    queue_name = retry_settings.fraud_scoring_queue
    handler = build_handler(settings=retry_settings, score_fn=always_fails)
    send(
        queue_name,
        {"determination_id": str(determination.determination_id)},
        settings=retry_settings,
    )

    assert poll_once(queue_name, handler, settings=retry_settings) is True
    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select count(*) from fraud_risk_score where determination_id = %s",
            (determination.determination_id,),
        )
        (count,) = cur.fetchone()  # type: ignore[misc]
        assert count == 0

    time.sleep(1.5)

    # Redelivered, not lost -- pgmq's own visibility-timeout expiry.
    message = read(queue_name, visibility_timeout_seconds=30, settings=retry_settings)
    assert message is not None
    assert message.message["determination_id"] == str(determination.determination_id)
    assert message.read_ct == 2
