"""document_intake_consumer.py's own orchestration -- read message, fetch
document row, call the classification capability, persist the result,
delete the message on success, leave it for retry on failure. The
capability itself (`canopica_ai.document_intake`'s real OCR/LLM call) has
its own coverage in ai/tests/test_document_intake.py, including the one
test that needs a real model; this file injects a stub in its place
(`build_handler`'s own `classify_and_extract_fn` parameter) so this
consumer's own wiring runs on every push against a real Postgres, with no
Ollama or MinIO required.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from datetime import date
from uuid import UUID

import psycopg
import pytest
from canopica_ai.document_intake.schema import DocumentExtraction, ExtractedField

from canopica_worker.config import Settings
from canopica_worker.document_intake_consumer import build_handler
from canopica_worker.main import poll_once
from canopica_worker.queue import read, send

pytestmark = pytest.mark.integration


class _ProgramRequest:
    def __init__(self, program_request_id: UUID) -> None:
        self.program_request_id = program_request_id


@pytest.fixture
def program_request(migrated_settings: Settings) -> Iterator[_ProgramRequest]:
    """The minimal person -> household -> application -> program_request
    chain `document`'s own foreign key requires, inserted directly via
    raw SQL (this suite has no Java-side CaseFixtures equivalent) --
    plus one OUTSTANDING income verification for the matching tests to
    resolve against."""
    person_id = uuid.uuid4()
    household_id = uuid.uuid4()
    application_id = uuid.uuid4()
    program_request_id = uuid.uuid4()
    verification_id = uuid.uuid4()

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
            "values (%s, %s, 'SNAP', 'PENDING_VERIFICATION', %s)",
            (program_request_id, application_id, date.today()),
        )
        cur.execute(
            "insert into verification (id, program_request_id, data_element, status, due_on) "
            "values (%s, %s, 'INCOME', 'OUTSTANDING', %s)",
            (verification_id, program_request_id, date.today()),
        )

    yield _ProgramRequest(program_request_id)


@pytest.fixture
def document_row(migrated_settings: Settings, program_request: _ProgramRequest) -> UUID:
    document_id = uuid.uuid4()
    object_key = f"{program_request.program_request_id}/{document_id}"
    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into document (id, program_request_id, object_key, content_type, uploaded_by) "
            "values (%s, %s, %s, 'application/pdf', 'worker.sam@canopica.local')",
            (document_id, program_request.program_request_id, object_key),
        )
    return document_id


def test_a_queued_message_is_classified_confirmed_persisted_and_the_message_deleted(
    migrated_settings: Settings, program_request: _ProgramRequest, document_row: UUID
) -> None:
    verification_id = _outstanding_verification_id(migrated_settings, program_request)
    extraction = DocumentExtraction(
        document_type="INCOME_REPORT",
        fields=[
            ExtractedField(name="employer_name", value="Acme Corp", confidence=0.95),
            ExtractedField(name="gross_monthly_income", value="2100", confidence=0.4),
        ],
        matched_verification_ids=[verification_id],
        generation_model="llama3.2:3b",
        prompt_version="v1",
    )

    def stub(object_key: str, content_type: str) -> DocumentExtraction:
        assert object_key == f"{program_request.program_request_id}/{document_row}"
        assert content_type == "application/pdf"
        return extraction

    queue_name = migrated_settings.document_intake_queue
    handler = build_handler(settings=migrated_settings, classify_and_extract_fn=stub)
    send(queue_name, {"document_id": str(document_row)}, settings=migrated_settings)

    found = poll_once(queue_name, handler, settings=migrated_settings)
    assert found is True

    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select classification_status, extraction_confidence, extraction->>'document_type' "
            "from document where id = %s",
            (document_row,),
        )
        status, confidence, document_type = cur.fetchone()  # type: ignore[misc]
        assert status == "CLASSIFIED"
        # The minimum across fields (0.4), not an average -- the lowest-
        # confidence field is what should drive review-queue urgency.
        assert float(confidence) == pytest.approx(0.4)
        assert document_type == "INCOME_REPORT"

        cur.execute(
            "select payload->>'document_id', payload->'matched_verification_ids' "
            "from audit_event where event_type = 'DOCUMENT_CLASSIFIED' and actor_id = 'SYSTEM' "
            "and subject_id = %s",
            (program_request.program_request_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == str(document_row)
        assert row[1] == [str(verification_id)]

    # The message was deleted on success, not left for redelivery.
    assert poll_once(queue_name, handler, settings=migrated_settings) is False


def test_a_classification_failure_leaves_the_message_for_retry_not_a_silent_drop(
    migrated_settings: Settings, program_request: _ProgramRequest, document_row: UUID
) -> None:
    retry_settings = migrated_settings.model_copy(
        update={"visibility_timeout_seconds": 1, "max_delivery_attempts": 5}
    )

    def always_fails(object_key: str, content_type: str) -> DocumentExtraction:
        raise RuntimeError("simulated classification failure")

    queue_name = retry_settings.document_intake_queue
    handler = build_handler(settings=retry_settings, classify_and_extract_fn=always_fails)
    send(queue_name, {"document_id": str(document_row)}, settings=retry_settings)

    assert poll_once(queue_name, handler, settings=retry_settings) is True
    with psycopg.connect(migrated_settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select classification_status from document where id = %s", (document_row,))
        assert cur.fetchone() == ("PENDING",)

    time.sleep(1.5)

    # Redelivered, not lost -- pgmq's own visibility-timeout expiry.
    message = read(queue_name, visibility_timeout_seconds=30, settings=retry_settings)
    assert message is not None
    assert message.message["document_id"] == str(document_row)
    assert message.read_ct == 2


def _outstanding_verification_id(settings: Settings, program_request: _ProgramRequest) -> UUID:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select id from verification where program_request_id = %s and status = 'OUTSTANDING'",
            (program_request.program_request_id,),
        )
        row = cur.fetchone()
        assert row is not None
        return UUID(str(row[0]))
