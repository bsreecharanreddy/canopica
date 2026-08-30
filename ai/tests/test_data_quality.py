"""Data-quality anomaly detection (Phase 4 Task 9, design doc §2.7).

`TestFindFailedTests`/`TestGatherContext` hand-build a tiny DuckDB file
with a `main.elementary_test_results` table matching the real schema
verified live (2026-08-30) against a real `dbt build` with the Elementary
package installed -- the same "hand-built known-answer warehouse, not a
live dbt/Testcontainers build" reasoning `test_analytics_copilot.py`'s own
docstring gives: this file only needs to prove *this* module reads that
table correctly, which `data-platform/tests/test_elementary.py`'s own
real `dbt build` already proves the table's real shape and contents for.
`TestSummarizeGuardRails`/`TestSummarizeGrounding` are pure unit tests, no
I/O, same shape every other grounded-draft capability's own tests take.
`TestRefreshDataQualityIncidents` is `@pytest.mark.e2e`: a stub LLM client
standing in for Ollama, against the real shared local dev Postgres, same
"real write, stubbed model" posture `test_sla_monitor.py`'s own
`TestRefreshStallReasons` already establishes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import psycopg
import pytest
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.data_quality.elementary_ingest import find_failed_tests
from canopica_ai.data_quality.root_cause import gather_context
from canopica_ai.data_quality.service import (
    SummaryDraftError,
    SummaryGroundingError,
    refresh_data_quality_incidents,
    summarize,
)

_INVOCATION_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_INVOCATION_ID = "22222222-2222-2222-2222-222222222222"


def _build_probe_warehouse(tmp_path: Path, rows: list[tuple[Any, ...]]) -> Path:
    """Column order/types match the real `main.elementary_test_results`
    schema observed live: id, data_issue_id, test_execution_id,
    test_unique_id, model_unique_id, invocation_id, detected_at,
    created_at, database_name, schema_name, table_name, column_name,
    test_type, test_sub_type, test_results_description, owners, tags,
    test_results_query, other, test_name, test_params, severity, status,
    failures, test_short_name, test_alias, result_rows, failed_row_count.
    """
    duckdb_path = tmp_path / "probe.duckdb"
    connection = duckdb.connect(str(duckdb_path))
    connection.execute("create schema if not exists main")
    connection.execute(
        """
        create table main.elementary_test_results (
            id varchar, data_issue_id varchar, test_execution_id varchar,
            test_unique_id varchar, model_unique_id varchar, invocation_id varchar,
            detected_at timestamp, created_at timestamp, database_name varchar,
            schema_name varchar, table_name varchar, column_name varchar,
            test_type varchar, test_sub_type varchar, test_results_description varchar,
            owners varchar, tags varchar, test_results_query varchar, other varchar,
            test_name varchar, test_params varchar, severity varchar, status varchar,
            failures bigint, test_short_name varchar, test_alias varchar,
            result_rows varchar, failed_row_count bigint
        )
        """
    )
    connection.executemany(
        "insert into main.elementary_test_results values "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    connection.close()
    return duckdb_path


def _row(  # noqa: PLR0913 -- a fixture-row builder, one keyword per real column that varies across tests
    *,
    test_unique_id: str = "test.canopica_warehouse.no_negative_processing_days",
    invocation_id: str = _INVOCATION_ID,
    detected_at: datetime,
    table_name: str = "mart_processing_timeliness",
    test_name: str = "no_negative_processing_days",
    test_type: str = "dbt_test",
    status: str = "fail",
    test_results_query: str | None = None,
) -> tuple[Any, ...]:
    row_id = f"{invocation_id}.{test_unique_id}"
    return (
        row_id, None, row_id, test_unique_id, None, invocation_id,
        detected_at, detected_at, "canopica", "main_gold", table_name, None,
        test_type, "singular", "Got 1 result, configured to fail if != 0", None, None,
        test_results_query, None, test_name, None, "error", status,
        1, test_name, None, None, 1,
    )


class TestFindFailedTests:
    def test_returns_only_this_invocations_own_non_passing_rows(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        duckdb_path = _build_probe_warehouse(
            tmp_path,
            [
                _row(detected_at=now, status="fail"),
                _row(test_unique_id="test.other.passing_test", detected_at=now, status="pass"),
                _row(test_unique_id="test.other.skipped_test", detected_at=now, status="skipped"),
                _row(detected_at=now, invocation_id=_OTHER_INVOCATION_ID, status="fail"),
            ],
        )

        failures = find_failed_tests(duckdb_path, invocation_id=_INVOCATION_ID)

        assert [f.test_unique_id for f in failures] == [
            "test.canopica_warehouse.no_negative_processing_days"
        ]

    def test_maps_test_type_to_source(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        duckdb_path = _build_probe_warehouse(
            tmp_path,
            [
                _row(test_unique_id="test.a", detected_at=now, test_type="dbt_test"),
                _row(test_unique_id="test.b", detected_at=now, test_type="anomaly_detection"),
            ],
        )

        failures = {
            f.test_unique_id: f.source
            for f in find_failed_tests(duckdb_path, invocation_id=_INVOCATION_ID)
        }

        assert failures == {"test.a": "dbt_test", "test.b": "elementary"}


class TestGatherContext:
    def test_failing_row_sample_re_runs_the_compiled_query(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        query = "select * from (values (1, 'a'), (2, 'b')) as t(id, name)"
        duckdb_path = _build_probe_warehouse(
            tmp_path, [_row(detected_at=now, test_results_query=query)]
        )
        [failure] = find_failed_tests(duckdb_path, invocation_id=_INVOCATION_ID)

        context = gather_context(duckdb_path, failure)

        assert context.model_name == "mart_processing_timeliness"
        assert context.failing_row_sample == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        assert context.historical_baseline == "This is the first recorded failure for this test."

    def test_a_prior_failure_is_reflected_in_the_baseline(self, tmp_path: Path) -> None:
        earlier = datetime.now(UTC) - timedelta(days=1)
        now = datetime.now(UTC)
        duckdb_path = _build_probe_warehouse(
            tmp_path,
            [
                _row(invocation_id=_OTHER_INVOCATION_ID, detected_at=earlier),
                _row(detected_at=now),
            ],
        )
        [failure] = find_failed_tests(duckdb_path, invocation_id=_INVOCATION_ID)

        context = gather_context(duckdb_path, failure)

        assert "failed 1 time(s) before" in context.historical_baseline

    def test_no_query_means_no_row_sample(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        duckdb_path = _build_probe_warehouse(
            tmp_path, [_row(detected_at=now, test_results_query=None)]
        )
        [failure] = find_failed_tests(duckdb_path, invocation_id=_INVOCATION_ID)

        context = gather_context(duckdb_path, failure)

        assert context.failing_row_sample == []


class _StubSummaryClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses: list[str | Exception] = list(responses)

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        next_response = self._responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return LlmResponse(text=next_response)


def _summary_json(summary: str) -> str:
    return json.dumps({"summary": summary})


class TestSummarizeGuardRails:
    def test_a_valid_grounded_response_becomes_the_summary(self) -> None:
        summary = summarize(
            "mart_processing_timeliness", "no_negative_processing_days", [], "first failure",
            llm_client=_StubSummaryClient(
                [
                    _summary_json(
                        "mart_processing_timeliness has a row with negative processing_days."
                    )
                ]
            ),
        )
        assert summary == "mart_processing_timeliness has a row with negative processing_days."

    def test_a_malformed_response_is_retried_once(self) -> None:
        summary = summarize(
            "mart_processing_timeliness", "no_negative_processing_days", [], "first failure",
            llm_client=_StubSummaryClient(
                ["not valid json", _summary_json("mart_processing_timeliness is affected.")]
            ),
        )
        assert summary == "mart_processing_timeliness is affected."

    def test_two_consecutive_malformed_responses_raise(self) -> None:
        with pytest.raises(SummaryDraftError):
            summarize(
                "mart_processing_timeliness", "no_negative_processing_days", [], "first failure",
                llm_client=_StubSummaryClient(["not valid json", "still not valid json"]),
            )


class TestSummarizeGrounding:
    def test_a_summary_that_never_names_the_real_model_is_retried_then_raises(self) -> None:
        ungrounded = _summary_json("Some upstream table has a data problem.")
        with pytest.raises(SummaryGroundingError):
            summarize(
                "mart_processing_timeliness", "no_negative_processing_days", [], "first failure",
                llm_client=_StubSummaryClient([ungrounded, ungrounded]),
            )

    def test_a_grounded_retry_after_an_ungrounded_first_attempt_succeeds(self) -> None:
        summary = summarize(
            "mart_processing_timeliness", "no_negative_processing_days", [], "first failure",
            llm_client=_StubSummaryClient(
                [
                    _summary_json("Some upstream table has a data problem."),
                    _summary_json("mart_processing_timeliness has an integrity violation."),
                ]
            ),
        )
        assert summary == "mart_processing_timeliness has an integrity violation."


def _ensure_incident_table(serving_dsn: str) -> None:
    """ai/ never imports data-platform's `materialize.py` (no cross-
    package Python import, per this repo's own established boundary --
    see `worker/`'s document_intake consumer for the one deliberate
    exception, which this isn't). This duplicates just enough of that
    function's own DDL for this test's own bootstrap; the real table is
    always actually created by `materialize.ensure_data_quality_incident_
    table`, which this DDL must keep matching."""
    with psycopg.connect(serving_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("create schema if not exists reporting")
        cur.execute(
            "create table if not exists reporting.data_quality_incident ("
            "id uuid primary key, source text not null, model_name text not null, "
            "test_or_check_name text not null, detected_at timestamptz not null, "
            "summary text not null, raw_context jsonb not null)"
        )


@pytest.mark.e2e
class TestRefreshDataQualityIncidents:
    def test_writes_a_real_incident_row_for_a_real_failure(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        _ensure_incident_table(settings.serving_dsn)
        now = datetime.now(UTC)
        # Uniquified for the same reason the grounding test below is: the
        # shared local dev Postgres is never truncated between runs.
        suffix = str(now.timestamp())
        invocation_id = f"e2e-{suffix}"
        test_unique_id = f"test.e2e.{suffix}"
        test_name = f"no_negative_processing_days_{suffix}"
        duckdb_path = _build_probe_warehouse(
            tmp_path,
            [_row(invocation_id=invocation_id, detected_at=now, test_unique_id=test_unique_id,
                  test_name=test_name)],
        )

        written = refresh_data_quality_incidents(
            invocation_id=invocation_id,
            duckdb_path=duckdb_path,
            settings=settings,
            llm_client=_StubSummaryClient(
                [_summary_json("mart_processing_timeliness has a negative processing_days row.")]
            ),
        )

        assert written == 1
        with psycopg.connect(settings.serving_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select model_name, source, summary from reporting.data_quality_incident "
                "where test_or_check_name = %s",
                (test_name,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "mart_processing_timeliness"
        assert row[1] == "dbt_test"

    def test_a_grounding_failure_on_one_test_does_not_abort_the_whole_run(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # This project's own shared local dev Postgres is never truncated
        # between test runs (the code-review skill's own rule 4) -- every
        # name below is suffixed with this run's own timestamp so a
        # count-based assertion can never be inflated by a leftover row
        # from an earlier run of this same test.
        _ensure_incident_table(settings.serving_dsn)
        now = datetime.now(UTC)
        suffix = str(now.timestamp())
        invocation_id = f"e2e-grounding-{suffix}"
        ungrounded_id = f"test.e2e.ungrounded.{suffix}"
        good_id = f"test.e2e.good.{suffix}"
        ungrounded_test_name = f"fixture_test_one_{suffix}"
        good_test_name = f"fixture_test_two_{suffix}"
        duckdb_path = _build_probe_warehouse(
            tmp_path,
            [
                _row(invocation_id=invocation_id, detected_at=now, test_unique_id=ungrounded_id,
                     table_name="fixture_model_one", test_name=ungrounded_test_name),
                _row(invocation_id=invocation_id, detected_at=now, test_unique_id=good_id,
                     table_name="fixture_model_two", test_name=good_test_name),
            ],
        )
        ungrounded = _summary_json("Some upstream table has a data problem.")

        written = refresh_data_quality_incidents(
            invocation_id=invocation_id,
            duckdb_path=duckdb_path,
            settings=settings,
            llm_client=_StubSummaryClient(
                [ungrounded, ungrounded, _summary_json("fixture_model_two has a real issue.")]
            ),
        )

        assert written == 1
        with psycopg.connect(settings.serving_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select count(*) from reporting.data_quality_incident "
                "where test_or_check_name = %s",
                (ungrounded_test_name,),
            )
            row_one = cur.fetchone()
            assert row_one is not None
            assert row_one[0] == 0
            cur.execute(
                "select count(*) from reporting.data_quality_incident "
                "where test_or_check_name = %s",
                (good_test_name,),
            )
            row_two = cur.fetchone()
            assert row_two is not None
            assert row_two[0] == 1
