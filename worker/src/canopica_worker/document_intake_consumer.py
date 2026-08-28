"""The `document_intake` queue's real handler (Task 3 plan, Step 5),
replacing `main.py`'s placeholder `_log_and_ack`. Reads a message, fetches
the `document` row, delegates classification to
`canopica_ai.document_intake.service.classify_and_extract` -- the sole
interface into that capability, per its own module docstring -- and
persists the result: `document.extraction`/`extraction_confidence`,
`classification_status = 'CLASSIFIED'`, and a `DOCUMENT_CLASSIFIED` audit
event.

Deliberately never catches `classify_and_extract`'s own exceptions:
letting them propagate is what makes `main.py`'s `poll_once` apply its one
retry/archive policy uniformly, whether the failure was a DB error here or
a classification failure inside `ai/` -- a processing failure leaves the
message for pgmq's own redelivery, never a silent drop (Task 3 plan's own
Step 5 requirement).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import psycopg
from canopica_ai.document_intake.schema import DocumentExtraction
from canopica_ai.document_intake.service import classify_and_extract

from canopica_worker.config import Settings
from canopica_worker.queue import Message

# Written by this consumer, never by Java's AuditService -- the hash chain
# is computed by a database trigger (V6 migration), not application code,
# so any writer with insert access can append safely. "SYSTEM", not a
# free-text identifier, because AuditEventResponse.java's own actorType
# derivation is a literal string match against exactly this value (same
# convention JdbcDeterminationService's own "SYSTEM" actor already uses).
_SYSTEM_ACTOR = "SYSTEM"

ClassifyAndExtract = Callable[[str, str], DocumentExtraction]


class DocumentNotFoundError(RuntimeError):
    """The message named a `document_id` with no matching row. Raised
    rather than silently skipped -- a document uploaded successfully
    (Task 2's own transactional guarantee) should always exist by the time
    this consumer reads its queued message, so a miss here is a real bug
    worth surfacing through the normal retry/archive path, not a case to
    special-case away."""


def _minimum_confidence(extraction: DocumentExtraction) -> float:
    """Drives Task 4's review-queue ordering (lowest confidence first) --
    the worst single field is what should draw a reviewer's attention
    first, not an average that a handful of confident fields could hide a
    dubious one behind. Zero fields extracted at all is the least
    confident outcome there is, not a null to sort arbitrarily."""
    if not extraction.fields:
        return 0.0
    return min(field.confidence for field in extraction.fields)


def _persist(document_id: str, extraction: DocumentExtraction, *, settings: Settings) -> None:
    """Assumes the row already exists -- `handle` below has already read it
    once (to get `object_key`/`content_type`) by the time this runs."""
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "update document set classification_status = 'CLASSIFIED', "
            "extraction = %s::jsonb, extraction_confidence = %s where id = %s",
            (extraction.model_dump_json(), _minimum_confidence(extraction), document_id),
        )
        cur.execute(
            "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
            "values ('DOCUMENT_CLASSIFIED', %s, 'program_request', "
            "(select program_request_id from document where id = %s), %s::jsonb)",
            (
                _SYSTEM_ACTOR,
                document_id,
                json.dumps(
                    {
                        "document_id": document_id,
                        "document_type": extraction.document_type,
                        "matched_verification_ids": [
                            str(vid) for vid in extraction.matched_verification_ids
                        ],
                    }
                ),
            ),
        )
        # Both writes commit together on the `with` block's clean exit --
        # same connection-context-manager-as-transaction pattern queue.py's
        # own functions already use. A failure partway (e.g. the insert
        # violating audit_event's own append-only trigger) rolls both back,
        # leaving classification_status at PENDING for the next retry.


def build_handler(
    *,
    settings: Settings | None = None,
    classify_and_extract_fn: ClassifyAndExtract = classify_and_extract,
) -> Callable[[Message], None]:
    """`classify_and_extract_fn` is injectable so this consumer's own
    orchestration (read row, call the capability, write the result) can be
    tested without a live Ollama -- the same reason `main.py`'s `Handler`
    type takes a plain callable rather than hardcoding one. The real
    extraction logic has its own coverage in `ai/tests/test_document_
    intake.py`, including the one test that needs a real model."""
    settings = settings or Settings()

    def handle(message: Message) -> None:
        document_id = message.message["document_id"]
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select object_key, content_type from document where id = %s",
                (document_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise DocumentNotFoundError(f"document {document_id} not found")
        object_key, content_type = row

        extraction = classify_and_extract_fn(object_key, content_type)

        _persist(document_id, extraction, settings=settings)

    return handle
