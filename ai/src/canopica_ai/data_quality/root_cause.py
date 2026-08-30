"""Gathers the structured failure context `service.summarize()` drafts
from -- a failing-row sample (re-running the exact query Elementary/dbt
already compiled for this test, so the sample is never separately
reconstructed) and a historical-baseline statement (has this same test
failed before, and when) -- for one `elementary_ingest.ElementaryFailure`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from canopica_ai.data_quality.elementary_ingest import ElementaryFailure

_SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class RootCauseContext:
    model_name: str
    test_or_check_name: str
    source: str
    failing_row_sample: list[dict[str, Any]]
    historical_baseline: str


def _failing_row_sample(
    connection: duckdb.DuckDBPyConnection, query: str | None
) -> list[dict[str, Any]]:
    if not query:
        return []
    # test_results_query is Elementary's/dbt's own compiled SQL for this
    # test, not free text -- wrapped rather than trusted to already carry
    # a LIMIT, since a wide failure (e.g. a schema-change test) could
    # otherwise return every failing row.
    result = connection.execute(f"select * from ({query}) as failing_rows limit {_SAMPLE_LIMIT}")
    columns = [description[0] for description in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def _historical_baseline(connection: duckdb.DuckDBPyConnection, failure: ElementaryFailure) -> str:
    row = connection.execute(
        "select count(*), max(detected_at) from main.elementary_test_results "
        "where test_unique_id = ? and status = 'fail' and detected_at < ?",
        [failure.test_unique_id, failure.detected_at],
    ).fetchone()
    prior_count, prior_last = row if row else (0, None)
    if not prior_count:
        return "This is the first recorded failure for this test."
    return f"This test has failed {prior_count} time(s) before, most recently at {prior_last}."


def gather_context(duckdb_path: Path, failure: ElementaryFailure) -> RootCauseContext:
    connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        return RootCauseContext(
            model_name=failure.model_name,
            test_or_check_name=failure.test_name,
            source=failure.source,
            failing_row_sample=_failing_row_sample(connection, failure.test_results_query),
            historical_baseline=_historical_baseline(connection, failure),
        )
    finally:
        connection.close()
