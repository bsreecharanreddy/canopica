"""Analytics Copilot (Task 5 plan; design doc §2.4, and the 2026-08-24
execution/authorization design doc's Option A).

Layered the same way the design doc's own four-layer session model is
laid out, cheapest/most-hermetic first:

* `TestMetricCatalog`/`TestQueryMetricArgs` -- no I/O, Task 4's real
  committed `metrics.yml` read directly.
* `TestLockedDownExecution` -- a real DuckDB file, no `mf`/dbt at all:
  proves the three session-enforcement controls actually hold (the design
  doc's own probe, repeated here as a regression test rather than a
  one-off manual check).
* `TestMetricQueryCorrectness`/`TestAskService`/`TestMcpServer` -- a real
  `dbt parse` + `mf query --explain` subprocess against a tiny, hand-built
  DuckDB warehouse (four rows, known answer) rather than Task 4's own
  Testcontainers-Postgres-and-dbt-build fixture: that fixture proves
  `mart_processing_timeliness`'s own SQL is correct, which is already
  covered by `data-platform/tests/test_mart_processing_timeliness.py` and
  Task 4's own `test_metric_semantics.py`. What this task needs to prove is
  narrower -- does the copilot turn a request into the *right* metric
  query and execute it correctly and safely -- and a hand-built warehouse
  with a known answer isolates exactly that, without `ai/` needing
  Testcontainers or data-platform's own ingestion package as a dependency
  (the same fixture-location reasoning Task 4's own test correction
  documented, applied in the other direction here).
* A live-Ollama `e2e` class proves the model itself resolves a real NL
  question to the right tool call -- everything below that line is
  request-shape/parsing, already covered without a live model in
  `test_llm_client.py`.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

import duckdb
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from pydantic import ValidationError

from canopica_ai.analytics_copilot import mcp_server, service
from canopica_ai.analytics_copilot.jwt_auth import WorkerClaims
from canopica_ai.analytics_copilot.metric_catalog import known_metric_names, load_known_metrics
from canopica_ai.analytics_copilot.metric_query import (
    MetricCompilationError,
    execute_readonly,
    run_metric_query,
)
from canopica_ai.analytics_copilot.tools import (
    QUERY_METRIC_TOOL_NAME,
    QueryMetricArgs,
    UnknownMetricError,
    tool_list_for_role,
)
from canopica_ai.common.llm_client import ToolCall, ToolSpec
from canopica_ai.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PLATFORM_ROOT = REPO_ROOT / "data-platform"
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"
DBT_BINARY = DATA_PLATFORM_ROOT / ".venv" / "bin" / "dbt"


def _build_probe_warehouse(tmp_path: Path) -> Settings:
    """A tiny, hand-built DuckDB warehouse with a known-answer
    `mart_processing_timeliness` -- the same four scenarios (3/10 days
    expedited, 15/35 days standard) `data-platform/tests/conftest.py`'s
    `seeded_timeliness_dsn` fixture seeds, so the expected numbers below
    (6.5, 25.0) are the same ones Task 4's own test already proves the
    real dbt SQL produces from real seeded data -- this fixture only needs
    to be self-consistent with itself, not re-derive that mart's logic."""
    duckdb_path = tmp_path / "probe.duckdb"
    connection = duckdb.connect(str(duckdb_path))
    connection.execute("CREATE SCHEMA main_gold")
    connection.execute(
        """
        CREATE TABLE main_gold.mart_processing_timeliness (
            determination_key BIGINT,
            program_request_key BIGINT,
            is_expedited BOOLEAN,
            submitted_at TIMESTAMP,
            decided_at TIMESTAMP,
            processing_days BIGINT,
            standard_days BIGINT,
            missed_standard BOOLEAN
        )
        """
    )
    connection.execute(
        """
        INSERT INTO main_gold.mart_processing_timeliness VALUES
        (1, 1, true,  '2026-01-01', '2026-01-04', 3,  7,  false),
        (2, 2, true,  '2026-01-01', '2026-01-11', 10, 7,  true),
        (3, 3, false, '2026-01-01', '2026-01-16', 15, 30, false),
        (4, 4, false, '2026-01-01', '2026-02-05', 35, 30, true)
        """
    )
    connection.close()

    settings = Settings(
        data_platform_dbt_project_dir=DBT_PROJECT_DIR,
        mf_binary_path=DATA_PLATFORM_ROOT / ".venv" / "bin" / "mf",
        duckdb_path=duckdb_path,
    )

    parse = subprocess.run(
        [str(DBT_BINARY), "parse", "--project-dir", str(DBT_PROJECT_DIR),
         "--profiles-dir", str(DBT_PROJECT_DIR), "--quiet"],
        env={**os.environ, "CANOPICA_DUCKDB_PATH": str(duckdb_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert parse.returncode == 0, parse.stdout + parse.stderr
    return settings


@pytest.fixture(scope="session")
def probe_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    # Session-scoped: every test in this module queries the same
    # known-answer warehouse read-only, so building it (a real `dbt parse`
    # subprocess) once rather than per test keeps this file's own wall
    # clock down -- the same concern the last two commits on this repo
    # were about (STATUS.md verification log, 2026-08-24).
    return _build_probe_warehouse(tmp_path_factory.mktemp("analytics_copilot_probe"))


class TestMetricCatalog:
    def test_known_metric_names_matches_task_4s_real_manifest(self) -> None:
        names = known_metric_names()

        assert "avg_processing_days" in names
        assert "active_case_count" in names
        assert len(names) == 13

    def test_every_metric_has_a_non_empty_description(self) -> None:
        for metric in load_known_metrics():
            assert metric.description


class TestQueryMetricArgs:
    def test_a_known_metric_name_is_accepted(self) -> None:
        args = QueryMetricArgs(metric_name="avg_processing_days")
        assert args.metric_name == "avg_processing_days"
        assert args.group_by == []

    def test_a_hallucinated_metric_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            QueryMetricArgs(metric_name="total_fraud_amount")

        assert any(
            issue["type"] == "value_error" and "total_fraud_amount" in str(issue["ctx"]["error"])
            for issue in excinfo.value.errors()
        )

    def test_unknown_metric_error_is_a_value_error(self) -> None:
        # Pydantic wraps it in ValidationError, but the underlying type
        # matters to a caller that wants to tell "hallucinated metric" apart
        # from any other validation failure.
        assert issubclass(UnknownMetricError, ValueError)


class TestToolListForRole:
    def test_worker_supervisor_and_admin_all_get_the_same_one_tool(self) -> None:
        for role in ("WORKER", "SUPERVISOR", "ADMIN"):
            [tool] = tool_list_for_role(role)
            assert tool.name == QUERY_METRIC_TOOL_NAME

    def test_a_role_with_no_analytics_access_gets_no_tools(self) -> None:
        assert tool_list_for_role("CUSTOMER") == []

    def test_the_tool_schema_names_every_known_metric(self) -> None:
        [tool] = tool_list_for_role("WORKER")
        for name in known_metric_names():
            assert name in tool.description


class TestLockedDownExecution:
    """The design doc's own probe table (§2, §3), repeated here as a
    regression test rather than a one-off manual check: a plain read-only
    DuckDB connection can still read arbitrary files off the host
    filesystem, which is why `enable_external_access=false` and
    `lock_configuration=true` are both load-bearing, not redundant with
    `read_only=True` alone."""

    @pytest.fixture
    def locked_down_path(self, tmp_path: Path) -> Path:
        path = tmp_path / "locked.duckdb"
        connection = duckdb.connect(str(path))
        connection.execute("CREATE TABLE t (n INTEGER)")
        connection.execute("INSERT INTO t VALUES (1), (2), (3)")
        connection.close()
        return path

    def test_a_normal_select_still_works(self, locked_down_path: Path) -> None:
        rows = execute_readonly("SELECT SUM(n) AS total FROM t", locked_down_path)
        assert rows == [{"total": 6}]

    def test_writes_are_rejected(self, locked_down_path: Path) -> None:
        with pytest.raises(duckdb.Error, match="read-only"):
            execute_readonly("CREATE TABLE x (a INT)", locked_down_path)

    def test_reading_an_arbitrary_external_file_is_rejected(self, locked_down_path: Path) -> None:
        # Not read_only=True's job -- that only blocks writes. This is
        # specifically what enable_external_access=false closes (design
        # doc §2's probe): a read-only connection can otherwise still read
        # any path the process can reach.
        with pytest.raises(duckdb.Error, match="disabled by configuration"):
            execute_readonly("SELECT * FROM read_csv('/etc/passwd')", locked_down_path)

    def test_the_lockdown_itself_cannot_be_loosened_mid_session(self) -> None:
        connection = duckdb.connect(
            ":memory:",
            read_only=False,
            config={"enable_external_access": "false", "lock_configuration": "true"},
        )
        try:
            with pytest.raises(duckdb.Error, match="locked"):
                connection.execute("SET enable_external_access = true")
        finally:
            connection.close()


class TestMetricQueryCorrectness:
    def test_compiles_and_executes_a_real_metric_query_correctly(
        self, probe_settings: Settings
    ) -> None:
        execution = run_metric_query(
            metric_names=["avg_processing_days"],
            group_by_names=["determination__is_expedited"],
            settings=probe_settings,
        )

        assert "avg_processing_days" in execution.compiled_sql
        by_expedited = {row["determination__is_expedited"]: row["avg_processing_days"]
                         for row in execution.rows}
        assert by_expedited == {True: 6.5, False: 25.0}

    def test_an_invalid_group_by_reference_fails_compilation_not_silently(
        self, probe_settings: Settings
    ) -> None:
        # Same real resolver error Task 4's own test hit first: a bare,
        # non-entity-qualified dimension name is rejected by name, not
        # silently coerced into something else.
        with pytest.raises(MetricCompilationError, match="is_expedited"):
            run_metric_query(
                metric_names=["avg_processing_days"],
                group_by_names=["is_expedited"],
                settings=probe_settings,
            )


def _rsa_keypair() -> tuple[rsa.RSAPrivateKey, RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _worker_jwt(private_key: rsa.RSAPrivateKey, *, roles: list[str]) -> str:
    now = int(time.time())
    claims = {
        "sub": "worker.sam",
        "iss": "http://localhost:8081/realms/canopica-workers",
        "iat": now,
        "exp": now + 300,
        "realm_access": {"roles": roles},
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


class _StubToolCallingClient:
    def __init__(self, call: ToolCall) -> None:
        self._call = call
        self.seen_prompt: str | None = None
        self.seen_tools: list[ToolSpec] | None = None

    def generate_tool_call(self, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall:
        self.seen_prompt = prompt
        self.seen_tools = list(tools)
        return self._call


class TestAskService:
    """`ask()`'s own orchestration -- JWT decoding is stubbed the same way
    `test_jwt_auth.py` stubs the JWKS fetch (a real signed token, a fake
    key source), so this class proves `ask()`'s wiring, not
    `decode_worker_token`'s correctness a second time."""

    @pytest.fixture(autouse=True)
    def _stub_jwt_decoding(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        def fake_decode(token: str, *, settings: Settings) -> WorkerClaims:
            payload = jwt.decode(token, options={"verify_signature": False})
            return WorkerClaims(
                subject=payload["sub"],
                roles=frozenset(payload.get("realm_access", {}).get("roles", [])),
            )

        monkeypatch.setattr(service, "decode_worker_token", fake_decode)
        yield

    def test_a_correct_answer_carries_metricflows_own_compiled_sql_and_rows(
        self, probe_settings: Settings
    ) -> None:
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        stub_llm = _StubToolCallingClient(
            ToolCall(
                name="query_metric",
                arguments={
                    "metric_name": "avg_processing_days",
                    "group_by": ["determination__is_expedited"],
                },
            )
        )

        answer = service.ask(
            "what is the average processing time by expedited status?",
            token,
            settings=probe_settings,
            llm_client=stub_llm,
        )

        assert answer.metric_names_used == ["avg_processing_days"]
        assert "avg_processing_days" in answer.compiled_sql
        by_expedited = {row["determination__is_expedited"]: row["avg_processing_days"]
                         for row in answer.result_rows}
        assert by_expedited == {True: 6.5, False: 25.0}
        # The tool list actually offered to the LLM was resolved before it
        # was ever called -- design doc §2.4's "authorization before query
        # compilation".
        assert stub_llm.seen_tools is not None
        [tool] = stub_llm.seen_tools
        assert tool.name == "query_metric"

    def test_a_hallucinated_metric_name_fails_validation_not_a_silent_fallback(
        self, probe_settings: Settings
    ) -> None:
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        stub_llm = _StubToolCallingClient(
            ToolCall(name="query_metric", arguments={"metric_name": "total_fraud_amount"})
        )

        with pytest.raises(ValidationError):
            service.ask(
                "how much fraud happened?", token, settings=probe_settings, llm_client=stub_llm
            )

    def test_a_caller_with_no_analytics_role_is_refused_before_any_llm_call(
        self, probe_settings: Settings
    ) -> None:
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["CUSTOMER"])
        stub_llm = _StubToolCallingClient(
            ToolCall(name="query_metric", arguments={"metric_name": "avg_processing_days"})
        )

        with pytest.raises(service.NoAccessibleMetricsError):
            service.ask("anything", token, settings=probe_settings, llm_client=stub_llm)

        assert stub_llm.seen_prompt is None


class TestMcpServer:
    def test_query_metric_is_registered_with_the_right_schema(self) -> None:
        [tool] = mcp_server.server._tool_manager.list_tools()

        assert tool.name == "query_metric"
        assert set(tool.parameters["properties"]) >= {"metric_name", "group_by", "filters"}

    def test_calling_the_tool_executes_a_real_locked_down_query(
        self, probe_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mcp_server, "Settings", lambda: probe_settings)

        result = mcp_server.query_metric(
            metric_name="avg_processing_days", group_by=["determination__is_expedited"]
        )

        by_expedited = {row["determination__is_expedited"]: row["avg_processing_days"]
                         for row in result["rows"]}
        assert by_expedited == {True: 6.5, False: 25.0}

    def test_calling_the_tool_with_a_hallucinated_metric_raises(self) -> None:
        with pytest.raises(ValueError, match="not a known metric"):
            mcp_server.query_metric(metric_name="total_fraud_amount")


_KEYCLOAK_URL = "http://localhost:8081"
_WORKER_USERNAME = "worker.sam"
_WORKER_PASSWORD = "CanopicaWorker123!"


def _live_worker_token() -> str:
    response = httpx.post(
        f"{_KEYCLOAK_URL}/realms/canopica-workers/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "test-worker",
            "client_secret": "test-worker-secret",
            "username": _WORKER_USERNAME,
            "password": _WORKER_PASSWORD,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


@pytest.mark.e2e
class TestAskWithARealModel:
    """The one thing nothing above proves: that a real Ollama model,
    given the real role-scoped tool list, actually picks the right metric
    and dimension for a real natural-language question. Everything else
    about `ask()` (JWT handling, validation, execution, security) is
    already proven without a live model above."""

    def test_a_real_question_resolves_to_the_correct_metric_and_number(
        self, tmp_path: Path
    ) -> None:
        settings = _build_probe_warehouse(tmp_path)
        token = _live_worker_token()

        answer = service.ask(
            "What is the average processing time for SNAP determinations, "
            "broken out by whether the determination was expedited?",
            token,
            settings=settings,
        )

        assert answer.metric_names_used == ["avg_processing_days"]
        by_expedited = {row["determination__is_expedited"]: row["avg_processing_days"]
                         for row in answer.result_rows}
        assert by_expedited == {True: 6.5, False: 25.0}
