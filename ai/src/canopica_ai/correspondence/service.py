"""AI-drafted correspondence (Task 5 plan): the sole interface the
worker's `correspondence_consumer.py` calls. Reads the determination's own
record (never recomputed -- design doc §2.4), picks a notice_type, drafts
the explanation slot via one LLM call, fills the chosen template
programmatically, and runs the deterministic pre-check -- never writes
anywhere itself. Same split `document_intake.service` holds: this module
drafts, the worker is what actually persists anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from string import Formatter
from typing import Any
from uuid import UUID

import psycopg

from canopica_ai.common.llm_client import StructuredLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.correspondence.draft import PROMPT_VERSION, draft_explanation
from canopica_ai.correspondence.schema import DeterminationRecord, NoticeDraft, NoticeType
from canopica_ai.correspondence.validate import validate

TEMPLATE_VERSION = "v1"

# Path-based, not importlib.resources: worker/pyproject.toml consumes this
# package as an editable path dependency (document_intake's own precedent,
# per its module docstring), so the source tree itself is what actually
# ends up on sys.path at runtime, not a built wheel -- a plain relative
# read against this file's own location is simpler and avoids depending
# on non-Python data files being correctly included in a wheel this
# project never actually builds.
_TEMPLATES_DIR = Path(__file__).parent / "templates"


class DeterminationNotFoundError(RuntimeError):
    """The message named a `determination_id` with no matching row. A
    determination commits and enqueues in the same transaction (design
    doc §2.2's outbox guarantee), so a miss here is a real bug worth
    surfacing through the normal retry/archive path, the same reasoning
    document_intake_consumer's own DocumentNotFoundError already gives."""


class _TolerantFormatter(Formatter):
    """Leaves an unresolved `{slot}` in place instead of raising
    `KeyError` -- turns a template/substitution mismatch into a
    reviewable `validate()` finding (its own unfilled-slot check) rather
    than a crashed worker message, per Step 6's own "a validation failure
    still produces a DRAFT row" requirement."""

    def get_value(self, key: object, args: Any, kwargs: Mapping[str, Any]) -> Any:
        if isinstance(key, str) and key in kwargs:
            return kwargs[key]
        return "{" + str(key) + "}"


def _fetch_determination(determination_id: UUID, *, settings: Settings) -> DeterminationRecord:
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select d.program_request_id, d.eligible, d.benefit_amount, d.reason_code, "
            "d.benefit_month, d.as_of_date, d.decided_at, "
            "t.input_snapshot, t.decision_results, "
            "p.first_name, p.last_name, "
            "exists(select 1 from verification v where v.program_request_id = d.program_request_id "
            "and v.status = 'OUTSTANDING') as has_outstanding_verification "
            "from eligibility_determination d "
            "join determination_trace t on t.determination_id = d.id "
            "join program_request r on r.id = d.program_request_id "
            "join application a on a.id = r.application_id "
            "join household h on h.id = a.household_id "
            "join person p on p.id = h.head_person_id "
            "where d.id = %s",
            (determination_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise DeterminationNotFoundError(f"determination {determination_id} not found")
    (
        program_request_id,
        eligible,
        benefit_amount,
        reason_code,
        benefit_month,
        as_of_date,
        decided_at,
        trace_facts,
        trace_decisions,
        first_name,
        last_name,
        has_outstanding_verification,
    ) = row
    return DeterminationRecord(
        determination_id=determination_id,
        program_request_id=program_request_id,
        eligible=eligible,
        benefit_amount=benefit_amount,
        reason_code=reason_code,
        benefit_month=benefit_month,
        as_of_date=as_of_date,
        decided_at=decided_at,
        trace_facts=trace_facts,
        trace_decisions=trace_decisions,
        household_head_name=f"{first_name} {last_name}",
        has_outstanding_verification=has_outstanding_verification,
    )


def _select_notice_type(determination: DeterminationRecord) -> NoticeType:
    """Task 5's only trigger is a determination commit, so this is the one
    place `notice_type` gets decided (design doc §4 leaves the exact
    selection to task-level judgment). A case still carrying an
    OUTSTANDING verification takes PENDING_VERIFICATION regardless of the
    eligible flag -- the DMN's own figure is real but provisional until
    the household's documentation is in, which is a materially different
    message than a settled approval or denial. Otherwise the determination
    speaks for itself: eligible -> APPROVAL, not eligible -> DENIAL."""
    if determination.has_outstanding_verification:
        return "PENDING_VERIFICATION"
    return "APPROVAL" if determination.eligible else "DENIAL"


def _load_template(notice_type: NoticeType) -> str:
    filename = f"{notice_type.lower()}.txt"
    return (_TEMPLATES_DIR / filename).read_text()


def fill_template(
    notice_type: NoticeType, determination: DeterminationRecord, explanation: str
) -> str:
    """Every slot but `explanation` is substituted programmatically from
    `determination` itself (design doc §2.4's central mechanism decision)
    -- public, and taking a plain `DeterminationRecord` rather than
    reading anything itself, so a synthetic fixture can exercise each
    `notice_type`'s own template without a real database or LLM."""
    template = _load_template(notice_type)
    return _TolerantFormatter().format(
        template,
        household_head_name=determination.household_head_name,
        benefit_month=determination.benefit_month.isoformat(),
        benefit_amount=f"${determination.benefit_amount:,.2f}",
        decided_at=determination.decided_at.date().isoformat(),
        explanation=explanation,
    )


def draft(
    determination_id: UUID,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> NoticeDraft:
    """Fetches the determination's own record, drafts the explanation,
    fills the chosen template, and runs the deterministic pre-check.
    Never writes to `notice` or the audit log -- that's the worker
    consumer's own job (Step 6)."""
    settings = settings or Settings()
    determination = _fetch_determination(determination_id, settings=settings)
    notice_type = _select_notice_type(determination)

    with traced_ai_operation("correspondence.draft"):
        explanation = draft_explanation(
            notice_type, determination, settings=settings, llm_client=llm_client
        )
        content = fill_template(notice_type, determination, explanation)
        validation_result = validate(content, determination)

    return NoticeDraft(
        notice_type=notice_type,
        content=content,
        template_version=TEMPLATE_VERSION,
        generation_model=settings.ollama_generation_model,
        prompt_version=PROMPT_VERSION,
        validation_result=validation_result,
    )
