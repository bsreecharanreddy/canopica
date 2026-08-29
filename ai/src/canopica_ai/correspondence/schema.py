"""What `service.draft` hands back to the worker consumer, and what the
consumer then inserts into `notice` verbatim (design doc §2.4/§2.6):
which template was used, the fully filled content, and the deterministic
pre-check's own verdict. Plain snake_case, same "nothing here crosses an
HTTP boundary" reasoning `document_intake.schema`'s own docstring gives --
Task 6's review-queue endpoint is what decides how this gets re-cast for
the wire, not this module.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

# The roadmap's own three-type list (design doc §2.4/§4). Task 5's only
# producer (a determination commit) can genuinely reach all three: see
# service.py's own selection docstring for why PENDING_VERIFICATION isn't
# dead code here.
NoticeType = Literal["APPROVAL", "DENIAL", "PENDING_VERIFICATION"]

# Task 7 (design doc §2.5): the languages a notice can be drafted in.
# `en` mirrors the `notice.language` column's own default, matching
# `ui/src/i18n/config.ts`'s `SUPPORTED_LANGUAGES` one-for-one so a
# citizen's chosen UI locale is always a language correspondence can
# actually be drafted in.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es")


class DeterminationRecord(BaseModel):
    """Everything `draft.py`'s explanation prompt and `validate.py`'s
    deterministic pre-check are grounded in -- read once, read-only, via a
    direct Postgres query in `service.py` (same boundary `document_intake.
    service`'s own `_matched_verification_ids` already uses for
    case-domain data this service has no write access to). `trace_facts`
    and `trace_decisions` are `determination_trace`'s own `input_snapshot`
    and `decision_results` columns, kept as loosely-typed dicts rather
    than a matching Pydantic model of the Java-side DMN shapes -- this
    module only ever reads numeric/date values out of them generically
    (`validate.py`'s own scan), never a named field, so there is nothing a
    stricter schema would buy here that the two dicts don't already give."""

    determination_id: UUID
    program_request_id: UUID
    eligible: bool
    benefit_amount: Decimal
    reason_code: str
    benefit_month: date
    as_of_date: date
    decided_at: datetime
    trace_facts: dict[str, Any]
    trace_decisions: dict[str, Any]
    household_head_name: str
    has_outstanding_verification: bool


class ValidationResult(BaseModel):
    """The deterministic pre-check's own verdict (design doc §2.4): every
    required slot filled, every number/date the content asserts traced
    back to `DeterminationRecord` itself, never LLM-judged. `errors` is
    empty exactly when `passed` is true -- kept as a list, not a single
    message, since more than one slot or figure can fail independently
    and a reviewer benefits from seeing all of them at once, not just the
    first."""

    passed: bool
    errors: list[str]


class NoticeDraft(BaseModel):
    """What `service.draft` returns -- the sole interface the worker
    consumer calls (Task 5 plan's own Interfaces note). A failed
    `validation_result` is still a real `NoticeDraft`, not an exception:
    Step 6's own requirement is that a validation failure still produces a
    reviewable `DRAFT` row, not a silently retried or dropped message."""

    notice_type: NoticeType
    content: str
    template_version: str
    language: str
    generation_model: str
    prompt_version: str
    validation_result: ValidationResult
