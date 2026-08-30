"""Deterministic days-remaining-ascending ranking (Phase 4 design doc
§2.4) -- explicitly not an LLM's job. Independently re-derives SNAP's
7-day-expedited/30-day-standard aging the same way `AtRiskCaseQuery.java`
(the live read path) and `mart_processing_timeliness.sql` (the
already-decided-case mart) already do: three implementations of the same
standard in three languages, cross-checked by their own tests rather than
shared via a library, the same deliberate duplication this project's
dbt/Java split already accepts elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

import psycopg

from canopica_ai.config import Settings


@dataclass(frozen=True)
class AtRiskCase:
    program_request_id: UUID
    requested_on: date
    is_expedited: bool
    days_remaining: int


def find_at_risk_cases(*, settings: Settings | None = None) -> list[AtRiskCase]:
    """Ordered most-urgent (smallest `days_remaining`) first -- the same
    order `AtRiskCaseQuery.findAtRiskCases` returns, so a case that runs
    out of refresh budget (a real, stated possibility, not handled by this
    function itself -- see `service.py`) drops the least urgent cases
    first, not an arbitrary subset."""
    settings = settings or Settings()
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select id, requested_on, is_expedited, "
            "(case when is_expedited then 7 else 30 end) "
            "- (current_date - requested_on) as days_remaining "
            "from program_request "
            "where status in ('SUBMITTED', 'PENDING_VERIFICATION') "
            "order by days_remaining asc"
        )
        rows = cur.fetchall()
    return [
        AtRiskCase(
            program_request_id=row[0], requested_on=row[1],
            is_expedited=row[2], days_remaining=row[3],
        )
        for row in rows
    ]
