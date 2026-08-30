"""Batch refresh entry point (Phase 4 Task 6 plan) -- called once per
Airflow task run, not per-request: `GET /api/sla/at-risk-queue` (Java)
reads `sla_stall_reason` directly and never calls into this module or an
LLM on its own request path (design doc §2.4).

Unlike `qc_assistant`/`correspondence` (each worker/pgmq-consumed, each
write coupled to a specific triggering transaction via the
transactional-outbox pattern), this module writes to Postgres directly
itself, the same direct-`psycopg`-write posture `worker/`'s own consumers
already use for their tables. There is no triggering write to couple an
outbox enqueue to here -- just a scheduled batch refresh over the
*current* at-risk set -- so the extra queue hop would add a moving part
with nothing for it to guarantee.

A single case's drafting or grounding failure does not abort the whole
refresh: `sla_stall_reason` is a cache the next scheduled run naturally
retries, not a queue with its own redelivery policy, so this logs the
failure and moves on to the next case rather than leaving every
still-good case's reason stale because one case's model output didn't
ground. This also covers a transient HTTP failure talking to Ollama
itself (`httpx.HTTPError`) -- live-measured, not hypothetical: a real run
against this project's own dev stack hit a genuine `500` from `ollama`
after processing 16 real cases over several sustained minutes of load,
which (before this was widened to catch it) crashed the entire batch
rather than skipping the one case mid-call when it happened. `OllamaClient`
itself has no retry of its own for this (only `OpenRouterTieredClient`,
Task 9's public-demo tier, does) -- same as every other capability in this
repo built on it, so this is the right layer to absorb it: one bad call
should cost this one case's refresh, not the other 15-plus that already
succeeded this run.

**A real, live-measured gap found running this for real (not assumed)**:
against this project's own shared local dev Postgres, `find_at_risk_cases`
returned 71 still-`SUBMITTED` rows -- every case any test/fixture across
this whole project's history has ever created and never transitioned out
of that status (`WorkerCaseController`'s own doc comment already notes no
code path moves it elsewhere today). Drafting one real LLM call per case,
unbounded, on every hourly run, took several real minutes for that count
alone and would only grow -- and re-drafting an unchanged case's reason
every single hour is wasted model-call cost regardless of dev-data
accumulation, the same "bounded, stated default" reasoning
`QcSamplingService.DEFAULT_SAMPLE_RATE` already establishes for a
different capability. `_DEFAULT_MAX_CASES_PER_RUN` bounds this run to the
most urgent cases (the population `find_at_risk_cases` already returns
most-urgent-first); a case with a reason already generated within
`_STALE_AFTER` is skipped (still refreshed if it's still within the
urgent slice covered by the run's own case cap, since that's exactly the
one place "up to date" matters most).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import httpx
import psycopg

from canopica_ai.common.llm_client import StructuredLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.sla_monitor.prioritize import AtRiskCase, find_at_risk_cases
from canopica_ai.sla_monitor.summarize import (
    StallReasonDraftError,
    StallReasonGroundingError,
    draft_grounded_stall_reason,
    gather_stall_context,
)

# Stated, unmeasured defaults -- same posture QcSamplingService.
# DEFAULT_SAMPLE_RATE and fraud_scoring_consumer's own _REVIEW_THRESHOLD
# already take. 50 covers a full workday's realistic at-risk queue depth
# without an open-ended per-run LLM-call count; 4 hours keeps a case's
# reason "current within the workday" (design doc §2.4's own phrase)
# without redrafting an unchanged case on every single hourly tick.
_DEFAULT_MAX_CASES_PER_RUN = 50
_STALE_AFTER = timedelta(hours=4)


def _needs_refresh(program_request_id: object, cur: psycopg.Cursor) -> bool:
    cur.execute(
        "select generated_at from sla_stall_reason where program_request_id = %s",
        (str(program_request_id),),
    )
    row = cur.fetchone()
    if row is None:
        return True
    generated_at: datetime = row[0]
    return datetime.now(UTC) - generated_at >= _STALE_AFTER


def refresh_stall_reasons(
    *,
    settings: Settings | None = None,
    max_cases_per_run: int = _DEFAULT_MAX_CASES_PER_RUN,
    llm_client: StructuredLlmClient | None = None,
    cases: list[AtRiskCase] | None = None,
) -> int:
    """Returns the number of cases whose `sla_stall_reason` row was
    written or updated this run. `llm_client` is injectable so this
    orchestration can be tested without a live Ollama -- same reason
    every worker consumer's own `build_handler` takes an injectable
    capability function. `cases` is injectable for the same reason, one
    level up: this project's own shared local dev Postgres accumulates
    real at-risk rows from every other test's own fixtures (the 71-row
    finding above), so a test asserting on its own specific case needs a
    way to bound the run to exactly the cases it created, not "whatever
    the live query returns today plus however many canned LLM responses
    happen to be queued." Airflow's real caller (`cli.py`) never passes
    this -- it always wants the live query."""
    settings = settings or Settings()
    if cases is None:
        cases = find_at_risk_cases(settings=settings)[:max_cases_per_run]
    written = 0
    for case in cases:
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            if not _needs_refresh(case.program_request_id, cur):
                continue
            context = gather_stall_context(case, cur)
            try:
                with traced_ai_operation("sla_monitor.summarize"):
                    reason = draft_grounded_stall_reason(
                        context, settings=settings, llm_client=llm_client
                    )
            except (StallReasonDraftError, StallReasonGroundingError, httpx.HTTPError) as error:
                print(
                    f"sla_monitor: skipping {case.program_request_id} this run: {error}",
                    file=sys.stderr,
                )
                continue
            cur.execute(
                "insert into sla_stall_reason (program_request_id, reason, generated_at) "
                "values (%s, %s, now()) "
                "on conflict (program_request_id) "
                "do update set reason = excluded.reason, generated_at = excluded.generated_at",
                (str(case.program_request_id), reason),
            )
            written += 1
    return written
