"""Failure -> summary pipeline step (Phase 4 Task 9, design doc §2.7):
when a `dbt test` fails or an Elementary anomaly fires, gather structured
context and draft a plain-language root-cause summary for a human to read
and investigate -- nothing here auto-remediates a pipeline failure
(constraint 19's spirit, applied to this component too), and this module
has no write path back into the warehouse or the operational database, only
an append to `reporting.data_quality_incident`.

`summarize()` is the one LLM call, matching the interface the design doc
names directly. `refresh_data_quality_incidents()` is the orchestration a
pipeline step calls after `dbt build`: find this invocation's own
failures, gather each one's context, draft a summary, insert one incident
row per failure.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import psycopg
from pydantic import BaseModel

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.data_quality.elementary_ingest import find_failed_tests
from canopica_ai.data_quality.root_cause import RootCauseContext, gather_context

# Same "one retry is worth it, two is evidence" reasoning every other
# grounded-draft call site in this repo already applies.
_MAX_ATTEMPTS = 2


class SummaryDraftError(RuntimeError):
    """The model could not produce a schema-valid summary after
    `_MAX_ATTEMPTS` tries."""


class SummaryGroundingError(RuntimeError):
    """The drafted summary never named the real model that actually
    failed -- raised rather than persisting a summary a reader could not
    trace back to the failure that produced it."""


class _DraftSummary(BaseModel):
    summary: str


def _prompt(
    model_name: str,
    test_or_check_name: str,
    failing_row_sample: list[dict[str, Any]],
    historical_baseline: str,
) -> str:
    sample_text = "\n".join(str(row) for row in failing_row_sample) or "(no row sample available)"
    return (
        "You are a data-quality analyst for a SNAP benefits data pipeline. A dbt test just "
        "failed. Write a short (2-3 sentence) plain-language root-cause summary for the "
        "engineer who will investigate it.\n\n"
        f"Model: {model_name}\n"
        f"Test: {test_or_check_name}\n"
        f"Sample of failing rows:\n{sample_text}\n"
        f"History: {historical_baseline}\n\n"
        "Rules that matter more than sounding polished:\n"
        f"- Name the real model ('{model_name}') in your summary, exactly as given above.\n"
        "- Describe what the sample rows suggest is wrong, using only what's actually shown -- "
        "never invent a cause the sample doesn't support.\n"
        "- This is a diagnostic aid for a human investigator, not an automated fix or a claim "
        "the root cause is certain.\n"
    )


def summarize(  # noqa: PLR0913 -- this exact 4-arg shape is the design doc's own named interface
    model_name: str,
    test_or_check_name: str,
    failing_row_sample: list[dict[str, Any]],
    historical_baseline: str,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    prompt = _prompt(model_name, test_or_check_name, failing_row_sample, historical_baseline)

    last_error: Exception | None = None
    draft_errors: list[str] = []
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftSummary)
        try:
            summary = _DraftSummary.model_validate_json(response.text).summary
        except ValueError as error:
            last_error = error
            continue

        if model_name.lower() in summary.lower():
            return summary
        draft_errors.append(
            f"summary never named the real failing model {model_name!r}: {summary!r}"
        )

    if draft_errors:
        raise SummaryGroundingError(
            f"drafted summary for {model_name}/{test_or_check_name} failed grounding after "
            f"{_MAX_ATTEMPTS} attempts: {draft_errors}"
        )
    raise SummaryDraftError(
        f"could not draft a summary for {model_name}/{test_or_check_name} after "
        f"{_MAX_ATTEMPTS} attempts: {last_error}"
    )


def _insert_incident(
    cur: psycopg.Cursor, context: RootCauseContext, summary: str, detected_at: Any
) -> None:
    cur.execute(
        "insert into reporting.data_quality_incident "
        "(id, source, model_name, test_or_check_name, detected_at, summary, raw_context) "
        "values (%s, %s, %s, %s, %s, %s, %s::jsonb)",
        (
            str(uuid.uuid4()),
            context.source,
            context.model_name,
            context.test_or_check_name,
            detected_at,
            summary,
            json.dumps(
                {
                    "failing_row_sample": context.failing_row_sample,
                    "historical_baseline": context.historical_baseline,
                },
                default=str,
            ),
        ),
    )


def refresh_data_quality_incidents(
    *,
    invocation_id: str,
    duckdb_path: Path | None = None,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> int:
    """Called once per pipeline run, after `dbt build` completes, with
    that build's own `invocation_id` (`run_results.json`'s
    `metadata.invocation_id`) -- scoping to one invocation is what keeps
    this idempotent-per-run without needing separate dedup state: a
    failure only ever gets summarized once, by the one run that produced
    it. Returns the number of incidents written.

    One failure's drafting/grounding trouble does not abort the whole
    refresh -- the same "log it, move to the next one" posture
    `sla_monitor.service.refresh_stall_reasons` already establishes (that
    module's own docstring records the real incident this guards against:
    a single transient Ollama 500 crashing an entire batch after several
    minutes of otherwise-successful work). A skipped failure is simply
    picked up by whichever *next* invocation next fails the same test --
    it is not lost, only deferred.
    """
    settings = settings or Settings()
    duckdb_path = duckdb_path or settings.duckdb_path

    failures = find_failed_tests(duckdb_path, invocation_id=invocation_id)
    if not failures:
        return 0

    written = 0
    with psycopg.connect(settings.serving_dsn, autocommit=True) as conn, conn.cursor() as cur:
        for failure in failures:
            context = gather_context(duckdb_path, failure)
            try:
                with traced_ai_operation("data_quality.summarize"):
                    summary = summarize(
                        context.model_name,
                        context.test_or_check_name,
                        context.failing_row_sample,
                        context.historical_baseline,
                        settings=settings,
                        llm_client=llm_client,
                    )
            except (SummaryDraftError, SummaryGroundingError, httpx.HTTPError) as error:
                print(
                    f"data_quality: skipping {failure.test_unique_id} this run: {error}",
                    file=sys.stderr,
                )
                continue
            _insert_incident(cur, context, summary, failure.detected_at)
            written += 1
    return written
