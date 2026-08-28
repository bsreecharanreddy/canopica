"""correspondence_consumer.py's own orchestration -- read a message, fetch
the determination's own program_request_id, call the drafting capability,
persist the result, delete the message on success, leave it for retry on
a genuine processing failure. The capability itself (`canopica_ai.
correspondence`'s real template-filling/pre-check logic) has its own
coverage in ai/tests/test_correspondence.py; this file injects a stub in
its place (`build_handler`'s own `draft_fn` parameter) so this consumer's
own wiring runs on every push against a real Postgres, with no Ollama
required -- same split test_document_intake_consumer.py's own module
docstring already establishes.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from uuid import UUID

import psycopg
import pytest
from canopica_ai.correspondence.schema import NoticeDraft, ValidationResult

from canopica_worker.config import Settings
from canopica_worker.correspondence_consumer import build_handler
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
    -> policy_parameter_set -> eligibility_determination -> determination_
    trace chain `notice`'s own foreign keys require, inserted directly via
    raw SQL -- this suite has no Java-side CaseFixtures equivalent."""
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
        # instance and a fixed literal date collided across them. Derived from parameter_set_id's
        # own freshly-generated UUID rather than a shared clock/counter, matching how every other
        # id in this fixture is already made unique.
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
        cur.execute(
            "insert into determination_trace "
            "(id, determination_id, input_snapshot, decision_results, dmn_model_name, "
            "dmn_model_hash, engine_version) "
            "values (%s, %s, '{}', '{}', 'snap-eligibility', 'test-hash', 'test')",
            (uuid.uuid4(), determination_id),
        )

    yield _Determination(determination_id, program_request_id)


def _draft_notice(*, passed: bool = True) -> NoticeDraft:
    return NoticeDraft(
        notice_type="APPROVAL",
        content="Dear Sam Applicant, your household is ELIGIBLE. Monthly benefit: $170.00.",
        template_version="v1",
        generation_model="llama3.2:3b",
        prompt_version="v1",
        validation_result=ValidationResult(
            passed=passed, errors=[] if passed else ["a deliberate test failure"]
        ),
    )


def test_a_queued_message_is_drafted_persisted_as_a_draft_notice_and_the_message_deleted(
    migrated_settings: Settings, determination: _Determination
) -> None:
    notice = _draft_notice()

    def stub(determination_id: UUID) -> NoticeDraft:
        assert determination_id == determination.determination_id
        return notice

    queue_name = migrated_settings.correspondence_dispatch_queue
    handler = build_handler(settings=migrated_settings, draft_fn=stub)
    send(
        queue_name,
        {"determination_id": str(determination.determination_id)},
        settings=migrated_settings,
    )

    found = poll_once(queue_name, handler, settings=migrated_settings)
    assert found is True

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select status, notice_type, content, template_version, generation_model, "
            "prompt_version, validation_result->>'passed' "
            "from notice where determination_id = %s",
            (determination.determination_id,),
        )
        row = cur.fetchone()
        assert row is not None
        (
            status,
            notice_type,
            content,
            template_version,
            generation_model,
            prompt_version,
            passed,
        ) = row
        assert status == "DRAFT"
        assert notice_type == "APPROVAL"
        assert content == notice.content
        assert template_version == "v1"
        assert generation_model == "llama3.2:3b"
        assert prompt_version == "v1"
        assert passed == "true"

        cur.execute(
            "select payload->>'determination_id', payload->>'notice_type', "
            "payload->>'validation_passed' "
            "from audit_event where event_type = 'NOTICE_DRAFTED' and actor_id = 'SYSTEM' "
            "and subject_id = %s",
            (determination.program_request_id,),
        )
        audit_row = cur.fetchone()
        assert audit_row is not None
        assert audit_row[0] == str(determination.determination_id)
        assert audit_row[1] == "APPROVAL"
        assert audit_row[2] == "true"

    # The message was deleted on success, not left for redelivery.
    assert poll_once(queue_name, handler, settings=migrated_settings) is False


def test_a_failed_validation_still_produces_a_draft_row_not_a_retry(
    migrated_settings: Settings, determination: _Determination
) -> None:
    """Step 6's own requirement: a deterministic-pre-check failure is a
    normal, reviewable outcome -- draft() itself never raises for one --
    so the message must still be deleted (never left for pgmq's own
    redelivery loop), and a human reviewer needs to see *why* it failed."""
    notice = _draft_notice(passed=False)

    def stub(determination_id: UUID) -> NoticeDraft:
        return notice

    queue_name = migrated_settings.correspondence_dispatch_queue
    handler = build_handler(settings=migrated_settings, draft_fn=stub)
    send(
        queue_name,
        {"determination_id": str(determination.determination_id)},
        settings=migrated_settings,
    )

    assert poll_once(queue_name, handler, settings=migrated_settings) is True

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select status, validation_result->>'passed', validation_result->'errors' "
            "from notice where determination_id = %s",
            (determination.determination_id,),
        )
        status, passed, errors = cur.fetchone()  # type: ignore[misc]
        assert status == "DRAFT"
        assert passed == "false"
        assert errors == ["a deliberate test failure"]

    # Not left for redelivery -- a failed validation is a completed outcome, not a processing error.
    assert poll_once(queue_name, handler, settings=migrated_settings) is False


def test_a_drafting_failure_leaves_the_message_for_retry_not_a_silent_drop(
    migrated_settings: Settings, determination: _Determination
) -> None:
    retry_settings = migrated_settings.model_copy(
        update={"visibility_timeout_seconds": 1, "max_delivery_attempts": 5}
    )

    def always_fails(determination_id: UUID) -> NoticeDraft:
        raise RuntimeError("simulated drafting failure")

    queue_name = retry_settings.correspondence_dispatch_queue
    handler = build_handler(settings=retry_settings, draft_fn=always_fails)
    send(
        queue_name,
        {"determination_id": str(determination.determination_id)},
        settings=retry_settings,
    )

    assert poll_once(queue_name, handler, settings=retry_settings) is True
    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select count(*) from notice where determination_id = %s",
            (determination.determination_id,),
        )
        assert cur.fetchone() == (0,)

    time.sleep(1.5)

    # Redelivered, not lost -- pgmq's own visibility-timeout expiry.
    message = read(queue_name, visibility_timeout_seconds=30, settings=retry_settings)
    assert message is not None
    assert message.message["determination_id"] == str(determination.determination_id)
    assert message.read_ct == 2
