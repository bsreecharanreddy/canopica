"""Reads Elementary's own on-run-end output (Phase 4 Task 9, design doc
§2.7) directly from the dbt-built DuckDB warehouse -- no Elementary CLI
(`edr`), no second tool, just SQL against a table Elementary's package
already writes as part of every `dbt build`.

Verified live (2026-08-30) against a real `dbt build` with the package
installed: the result table lands at ``main.elementary_test_results``,
the project's own base schema -- *not* a nested ``elementary``/
``main_elementary`` schema, contrary to what the docs alone would suggest.
Also verified live: this project's `dbt_project.yml` deliberately adds no
``on-run-end: - "{{ elementary.on_run_end() }}"`` hook of its own -- the
`elementary` package already defines that exact hook in its own
`dbt_project.yml`, and dbt runs every installed package's own hooks
automatically. Adding it a second time here was tried and confirmed (via
duplicate rows in a real build) to double-execute it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

# Elementary's own anomaly-detection tests set this exact value
# (store_anomaly_test_results.sql); every other test (dbt-native
# not_null/unique/accepted_values/relationships, and a plain singular
# test like no_negative_processing_days.sql) gets "dbt_test" from
# elementary.get_test_type(). Verified live against a real build rather
# than assumed from the package's docs.
_ELEMENTARY_TEST_TYPE = "anomaly_detection"


@dataclass(frozen=True)
class ElementaryFailure:
    test_unique_id: str
    model_name: str
    test_name: str
    source: str  # "dbt_test" or "elementary" -- design doc §2.8's own column name/values
    status: str
    failed_row_count: int | None
    test_results_description: str | None
    test_results_query: str | None
    detected_at: datetime


def _source_for(test_type: str) -> str:
    return "elementary" if test_type == _ELEMENTARY_TEST_TYPE else "dbt_test"


def find_failed_tests(duckdb_path: Path, *, invocation_id: str) -> list[ElementaryFailure]:
    """Every test result from one dbt invocation that did not pass --
    `status not in ('pass', 'skipped')` covers both a hard `fail` and a
    `warn`-severity anomaly, deliberately excluding `skipped` (a test that
    never ran because an upstream node errored is not itself a data-quality
    finding to summarize)."""
    connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        rows = connection.execute(
            "select test_unique_id, table_name, test_name, test_type, status, "
            "failed_row_count, test_results_description, test_results_query, detected_at "
            "from main.elementary_test_results "
            "where invocation_id = ? and status not in ('pass', 'skipped') "
            "order by detected_at",
            [invocation_id],
        ).fetchall()
        return [
            ElementaryFailure(
                test_unique_id=row[0],
                model_name=row[1],
                test_name=row[2],
                source=_source_for(row[3]),
                status=row[4],
                failed_row_count=row[5],
                test_results_description=row[6],
                test_results_query=row[7],
                detected_at=row[8],
            )
            for row in rows
        ]
    finally:
        connection.close()
