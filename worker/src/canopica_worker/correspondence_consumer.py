"""The `correspondence_dispatch` queue's real handler (Task 5 plan, Step
6), replacing `main.py`'s placeholder `_log_and_ack`. Reads a message,
delegates drafting to `canopica_ai.correspondence.service.draft` -- the
sole interface into that capability, per its own module docstring -- and
persists the result: a new `notice` row (always `status = 'DRAFT'`, even
when the deterministic pre-check failed -- Step 6's own requirement is
that a validation failure still produces a reviewable draft, not a
silently retried or dropped message) plus a `NOTICE_DRAFTED` audit event.

Deliberately never catches `service.draft`'s own exceptions (a genuine
processing failure -- determination not found, the LLM unable to produce
a schema-valid explanation after its own retries): letting those
propagate is what makes `main.py`'s `poll_once` apply its one retry/
archive policy uniformly, the same reasoning document_intake_consumer's
own module docstring already gives. A *validation* failure is a
different, expected outcome, not an exception -- `service.draft` itself
never raises for one.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import UUID

import psycopg
from canopica_ai.correspondence.schema import NoticeDraft
from canopica_ai.correspondence.service import draft

from canopica_worker.config import Settings
from canopica_worker.queue import Message

# Same convention document_intake_consumer.py's own _SYSTEM_ACTOR
# establishes: written by this consumer, keyed by AuditEventResponse.
# java's literal actorType match.
_SYSTEM_ACTOR = "SYSTEM"

Draft = Callable[[UUID], NoticeDraft]


class DeterminationNotFoundError(RuntimeError):
    """The message named a `determination_id` with no matching row. A
    determination commits and enqueues in the same transaction (design
    doc §2.2's outbox guarantee), so a miss here is a real bug worth
    surfacing through the normal retry/archive path -- same reasoning
    document_intake_consumer's own DocumentNotFoundError already gives."""


def _program_request_id(determination_id: str, *, settings: Settings) -> str:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select program_request_id from eligibility_determination where id = %s",
            (determination_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise DeterminationNotFoundError(f"determination {determination_id} not found")
    return str(row[0])


def _persist(
    program_request_id: str, determination_id: str, notice: NoticeDraft, *, settings: Settings
) -> None:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into notice (program_request_id, determination_id, notice_type, status, "
            "content, template_version, generation_model, prompt_version, validation_result) "
            "values (%s, %s, %s, 'DRAFT', %s, %s, %s, %s, %s::jsonb) returning id",
            (
                program_request_id,
                determination_id,
                notice.notice_type,
                notice.content,
                notice.template_version,
                notice.generation_model,
                notice.prompt_version,
                notice.validation_result.model_dump_json(),
            ),
        )
        row = cur.fetchone()
        assert row is not None
        notice_id = row[0]
        cur.execute(
            "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
            "values ('NOTICE_DRAFTED', %s, 'program_request', %s, %s::jsonb)",
            (
                _SYSTEM_ACTOR,
                program_request_id,
                json.dumps(
                    {
                        "notice_id": str(notice_id),
                        "determination_id": determination_id,
                        "notice_type": notice.notice_type,
                        "validation_passed": notice.validation_result.passed,
                    }
                ),
            ),
        )
        # Both writes commit together on the `with` block's clean exit --
        # same connection-context-manager-as-transaction pattern document_
        # intake_consumer.py's own _persist already uses.


def build_handler(
    *,
    settings: Settings | None = None,
    draft_fn: Draft = draft,
) -> Callable[[Message], None]:
    """`draft_fn` is injectable so this consumer's own orchestration (read
    the determination, call the capability, write the result) can be
    tested without a live Ollama -- same reason document_intake_consumer's
    own `build_handler` takes `classify_and_extract_fn`. The real drafting
    logic has its own coverage in `ai/tests/test_correspondence.py`."""
    settings = settings or Settings()

    def handle(message: Message) -> None:
        determination_id = message.message["determination_id"]
        program_request_id = _program_request_id(determination_id, settings=settings)

        notice = draft_fn(UUID(determination_id))

        _persist(program_request_id, determination_id, notice, settings=settings)

    return handle
