"""One-line stall-reason drafting (Phase 4 design doc §2.4) -- the one
LLM call this capability makes, grounded in the case's own outstanding
`verification` rows and its most recent `audit_event` entry, never an
invented cause. Same "compose from real fields, deterministically check
before trusting" discipline `qc_assistant/draft.py`+`validate.py`
establish for a different capability; kept in one file here rather than a
separate `validate.py` since Task 6's own file list names only three
modules and nothing forced the split the way Task 4's own grounding
requirement did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import psycopg
from pydantic import BaseModel

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.config import Settings
from canopica_ai.sla_monitor.prioritize import AtRiskCase

PROMPT_VERSION = "v1"

# Same "one retry is worth it, two is evidence" reasoning document_intake's
# own classify.py and qc_assistant's own draft.py already apply.
_MAX_ATTEMPTS = 2

# verification.data_element's own CHECK constraint (V2 migration) --
# the complete, exhaustive set a grounding check can compare a drafted
# reason's own capitalized mentions against.
_VERIFICATION_TYPES: tuple[str, ...] = (
    "IDENTITY", "RESIDENCY", "INCOME", "SHELTER_COST", "MEDICAL_EXPENSE",
    "DISABILITY", "HOUSEHOLD_COMPOSITION",
)

_DAY_COUNT_PATTERN = re.compile(r"(\d+)\s+days?\b")
_VERIFICATION_TYPE_PATTERN = re.compile(
    "|".join(_VERIFICATION_TYPES), re.IGNORECASE
)


@dataclass(frozen=True)
class StallContext:
    program_request_id: UUID
    days_remaining: int
    outstanding_verification_types: tuple[str, ...]
    last_audit_event_type: str | None
    days_since_last_audit_event: int | None


class StallReasonDraftError(RuntimeError):
    """The model could not produce a schema-valid reason after
    `_MAX_ATTEMPTS` tries. Raised rather than falling back to a canned
    string, same posture `qc_assistant.draft.SummaryDraftError` already
    establishes."""


class StallReasonGroundingError(RuntimeError):
    """The drafted reason named a verification type that isn't actually
    outstanding for this case, or a day count that matches neither
    `days_remaining` nor `days_since_last_audit_event`, after every retry
    -- raised rather than persisting a possibly-invented reason, same
    posture `qc_assistant.service.SummaryGroundingError` already
    establishes for a different capability."""


class _DraftReason(BaseModel):
    reason: str


def gather_stall_context(
    case: AtRiskCase, cur: psycopg.Cursor, *, today: date | None = None
) -> StallContext:
    """Reuses the caller's own open cursor/transaction (`service.py`'s
    batch loop) rather than opening a second connection per case."""
    today = today or date.today()
    cur.execute(
        "select data_element from verification "
        "where program_request_id = %s and status = 'OUTSTANDING'",
        (str(case.program_request_id),),
    )
    outstanding = tuple(row[0] for row in cur.fetchall())

    cur.execute(
        "select event_type, occurred_at from audit_event "
        "where subject_type = 'program_request' and subject_id = %s "
        "order by occurred_at desc limit 1",
        (str(case.program_request_id),),
    )
    row = cur.fetchone()
    last_event_type: str | None = None
    days_since_last_event: int | None = None
    if row is not None:
        last_event_type = row[0]
        occurred_at: datetime = row[1]
        days_since_last_event = (today - occurred_at.date()).days

    return StallContext(
        program_request_id=case.program_request_id,
        days_remaining=case.days_remaining,
        outstanding_verification_types=outstanding,
        last_audit_event_type=last_event_type,
        days_since_last_audit_event=days_since_last_event,
    )


def _prompt(context: StallContext) -> str:
    outstanding = ", ".join(context.outstanding_verification_types) or "none recorded"
    last_action = (
        f"{context.last_audit_event_type} ({context.days_since_last_audit_event} days ago)"
        if context.last_audit_event_type is not None
        else "no recorded activity yet"
    )
    return (
        "You are drafting a single short sentence for a SNAP supervisor's at-risk case queue, "
        "explaining why this application is still pending review.\n\n"
        f"Days remaining before this case misses its processing standard: "
        f"{context.days_remaining}\n"
        f"Outstanding verification types for this case: {outstanding}\n"
        f"Most recent case activity: {last_action}\n\n"
        "Rules that matter more than sounding polished:\n"
        "- Use ONLY the verification type names and day counts given above. Never introduce a "
        "verification type or a day count that isn't already stated there.\n"
        "- One short sentence, plain language, no jargon.\n"
    )


def draft_stall_reason(
    context: StallContext,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    prompt = _prompt(context)

    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftReason)
        try:
            return _DraftReason.model_validate_json(response.text).reason
        except ValueError as error:
            last_error = error
            continue

    raise StallReasonDraftError(
        f"could not draft a stall reason for {context.program_request_id} after "
        f"{_MAX_ATTEMPTS} attempts: {last_error}"
    )


def grounding_errors(reason: str, context: StallContext) -> list[str]:
    errors: list[str] = []

    known_day_counts = {context.days_remaining}
    if context.days_since_last_audit_event is not None:
        known_day_counts.add(context.days_since_last_audit_event)
    for match in _DAY_COUNT_PATTERN.findall(reason):
        if int(match) not in known_day_counts:
            errors.append(
                f"reason states '{match} days', which matches no real day count for this case"
            )

    for match in _VERIFICATION_TYPE_PATTERN.findall(reason):
        if match.upper() not in context.outstanding_verification_types:
            errors.append(
                f"reason mentions {match.upper()} verification, which is not actually outstanding "
                "for this case"
            )

    return errors


def draft_grounded_stall_reason(
    context: StallContext,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    last_errors: list[str] = []
    for _ in range(_MAX_ATTEMPTS):
        reason = draft_stall_reason(context, settings=settings, llm_client=llm_client)
        last_errors = grounding_errors(reason, context)
        if not last_errors:
            return reason

    raise StallReasonGroundingError(
        f"drafted stall reason for {context.program_request_id} failed grounding after "
        f"{_MAX_ATTEMPTS} attempts: {last_errors}"
    )
