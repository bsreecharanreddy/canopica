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
        # Phase 4 Task 8 added 5: rejected_determinations, notices,
        # rejected_notices, reviewed_notices, notice_rejection_rate.
        assert len(names) == 18

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

    def test_a_json_encoded_string_group_by_is_coerced_to_a_list(self) -> None:
        # Observed live in CI (2026-08-24): llama3.2:3b's tool call
        # returned group_by as the *string* '["determination__is_expedited"]'
        # rather than a native JSON array, even though the tool schema
        # declares it as an array. A real production failure mode, not
        # just a test flake -- the same shape would misfire on a live
        # worker's real question. model_validate (not the typed
        # constructor) matches the real call site: service.py calls
        # QueryMetricArgs.model_validate(call.arguments), an untyped dict
        # straight from the model's tool call.
        args = QueryMetricArgs.model_validate(
            {
                "metric_name": "avg_processing_days",
                "group_by": '["determination__is_expedited"]',
            }
        )
        assert args.group_by == ["determination__is_expedited"]

    def test_a_json_encoded_string_filters_is_coerced_to_a_list(self) -> None:
        args = QueryMetricArgs.model_validate(
            {"metric_name": "avg_processing_days", "filters": '["SNAP"]'}
        )
        assert args.filters == ["SNAP"]

    def test_a_python_repr_style_string_group_by_is_also_coerced_to_a_list(self) -> None:
        # Observed live (2026-08-25, a 10-sample real-model batch, on 5 of
        # 5 corrective retries): the model answered with group_by as the
        # *single-quoted* string "['determination__is_expedited']" --
        # Python's repr() style, not JSON (which requires double quotes).
        # json.loads rejects it outright, so the JSON coercion above never
        # even applies. A second, narrow fallback: only accepted if it
        # actually parses as a Python literal *and* that literal is a
        # list -- same "narrowly tolerated" shape as the JSON coercion,
        # just for the other quoting style this model also produces.
        args = QueryMetricArgs.model_validate(
            {
                "metric_name": "avg_processing_days",
                "group_by": "['determination__is_expedited']",
            }
        )
        assert args.group_by == ["determination__is_expedited"]

    def test_a_non_json_string_group_by_still_fails_validation(self) -> None:
        # The coercion is narrow: a string that isn't a JSON array is not
        # silently accepted, just because it happens to be a string.
        with pytest.raises(ValidationError):
            QueryMetricArgs.model_validate(
                {"metric_name": "avg_processing_days", "group_by": "not json at all"}
            )

    def test_a_filter_that_verbatim_repeats_a_group_by_dimension_is_rejected(self) -> None:
        # Observed live (2026-08-25, sampling llama3.2:3b 8 times against
        # one real question): 3 of 8 tool calls grouped by
        # determination__is_expedited *and* also filtered on the bare
        # dimension name with no comparison -- e.g. filters=
        # ["determination__is_expedited"]. That compiles (a bare boolean
        # column is a valid, if useless, `WHERE` clause) and silently
        # drops every False row instead of failing loudly -- worse than a
        # crash, because nothing ever complains. Grouping by a dimension
        # already includes every value of it, so a bare filter repeating
        # it is never a real narrowing filter.
        with pytest.raises(ValidationError, match="determination__is_expedited"):
            QueryMetricArgs.model_validate(
                {
                    "metric_name": "avg_processing_days",
                    "group_by": ["determination__is_expedited"],
                    "filters": ["determination__is_expedited"],
                }
            )

    def test_an_equality_filter_on_a_grouped_dimension_is_also_rejected(self) -> None:
        # The *dominant* live shape (2026-08-25, a second sampling batch:
        # 6 of 6 real calls), and not caught by the bare-repeat check
        # above: a real comparison, "determination__is_expedited = true",
        # against the exact dimension already in group_by. Still wrong for
        # the same reason a bare repeat is wrong -- an equality filter on
        # the dimension you're grouping by can only ever leave one group
        # standing, defeating the entire point of "broken out by X". The
        # rule keys on which *dimension* a filter targets, not on whether
        # it happens to have a comparison operator.
        with pytest.raises(ValidationError, match="determination__is_expedited"):
            QueryMetricArgs.model_validate(
                {
                    "metric_name": "avg_processing_days",
                    "group_by": ["determination__is_expedited"],
                    "filters": ["determination__is_expedited = true"],
                }
            )

    def test_a_comparison_filter_on_a_different_dimension_is_still_allowed(self) -> None:
        # The rule is narrow: it keys on the filter's *dimension* matching
        # a group_by entry, not "any filter alongside any group_by." A
        # filter narrowing a *different* dimension than the one being
        # grouped by is a completely ordinary, legitimate query shape
        # (e.g. "average by outcome, but only for SNAP") and must stay
        # allowed.
        args = QueryMetricArgs.model_validate(
            {
                "metric_name": "avg_processing_days",
                "group_by": ["determination__is_expedited"],
                "filters": ["determination__program_code = 'SNAP'"],
            }
        )
        assert args.filters == ["determination__program_code = 'SNAP'"]


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


class _SequencedToolCallingClient:
    """Returns one `ToolCall` per call, in order -- proves `ask()`'s
    corrective-retry path, which must send a *second*, different prompt
    (carrying the compiler's own rejection) rather than asking the same
    question twice. Raises `IndexError` on a call past the end of the
    sequence, which is deliberate: it turns "retried more times than
    intended" into a test failure instead of a silent extra LLM call."""

    def __init__(self, calls: Sequence[ToolCall]) -> None:
        self._calls = list(calls)
        self.seen_prompts: list[str] = []
        self.seen_tools: list[ToolSpec] | None = None

    def generate_tool_call(self, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall:
        self.seen_prompts.append(prompt)
        self.seen_tools = list(tools)
        return self._calls[len(self.seen_prompts) - 1]


class TestCorrectiveRetryPrompt:
    def test_the_previous_call_is_rendered_as_json_not_python_repr(self) -> None:
        # Observed live (2026-08-25, a 10-sample real-model batch): 5 of 5
        # retries came back with group_by as a single-quoted Python-repr
        # string ("['determination__is_expedited']") instead of JSON --
        # not valid JSON, so the existing coercion for a *JSON-encoded*
        # string doesn't accept it, and every one of those retries then
        # failed validation a second time. Root cause: the retry prompt
        # itself showed the model `str(dict)`/`repr(dict)` (Python's
        # single-quoted style, via an f-string's `!r`), which primed the
        # model to mimic that same non-JSON style right back. The prompt
        # must render the previous call's arguments as real JSON (double
        # quotes) so there is nothing double-quote-shaped to imitate
        # incorrectly.
        call = ToolCall(
            name="query_metric",
            arguments={
                "metric_name": "determinations",
                "group_by": ["determination__is_expedited"],
            },
        )
        prompt = service._corrective_retry_prompt(
            "a question", call, MetricCompilationError("some rejection")
        )

        assert "'determination__is_expedited'" not in prompt
        assert '"determination__is_expedited"' in prompt


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

    def test_a_compile_error_triggers_one_corrective_retry_and_then_succeeds(
        self, probe_settings: Settings
    ) -> None:
        """A real, observed failure mode (2026-08-25 CI): a small local
        model asked for the count metric `determinations` grouped by
        `determination__is_expedited`, a dimension that metric's semantic
        model doesn't have. MetricFlow's own compile error already lists
        the valid group-by items for what was asked; `ask()` must feed
        that error back and give the model one more try rather than
        failing on the first wrong guess."""
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        stub_llm = _SequencedToolCallingClient(
            [
                ToolCall(
                    name="query_metric",
                    arguments={
                        "metric_name": "determinations",
                        "group_by": ["determination__is_expedited"],
                    },
                ),
                ToolCall(
                    name="query_metric",
                    arguments={
                        "metric_name": "avg_processing_days",
                        "group_by": ["determination__is_expedited"],
                    },
                ),
            ]
        )

        answer = service.ask(
            "What is the average processing time broken out by expedited status?",
            token,
            settings=probe_settings,
            llm_client=stub_llm,
        )

        assert answer.metric_names_used == ["avg_processing_days"]
        by_expedited = {
            row["determination__is_expedited"]: row["avg_processing_days"]
            for row in answer.result_rows
        }
        assert by_expedited == {True: 6.5, False: 25.0}
        assert len(stub_llm.seen_prompts) == 2
        # The retry prompt must actually carry the compiler's own
        # rejection -- otherwise the model has no more information on the
        # second try than it had on the first.
        retry_prompt = stub_llm.seen_prompts[1]
        assert "determinations" in retry_prompt
        assert "does not match any of the available group-by-items" in retry_prompt

    def test_a_persistent_compile_error_still_fails_after_one_retry(
        self, probe_settings: Settings
    ) -> None:
        """The retry is a second chance, not a suppression: a model that
        makes the same mistake twice must still fail the caller, the same
        way a condition that never clears must still fail a CI gate."""
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        bad_call = ToolCall(
            name="query_metric",
            arguments={
                "metric_name": "determinations",
                "group_by": ["determination__is_expedited"],
            },
        )
        stub_llm = _SequencedToolCallingClient([bad_call, bad_call])

        with pytest.raises(MetricCompilationError):
            service.ask(
                "What is the average processing time broken out by expedited status?",
                token,
                settings=probe_settings,
                llm_client=stub_llm,
            )

        assert len(stub_llm.seen_prompts) == 2

    def test_a_redundant_bare_filter_triggers_a_corrective_retry_and_then_succeeds(
        self, probe_settings: Settings
    ) -> None:
        """A second real, observed failure mode (2026-08-25, live
        sampling): the model grouped by the right dimension but *also*
        filtered on it verbatim -- a mistake `QueryMetricArgs` now rejects
        at validation (see `TestQueryMetricArgs`). That validation error
        must feed the same corrective-retry path as a `MetricCompilationError`,
        not just a compiler rejection -- the model gets a real second
        chance either way."""
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        stub_llm = _SequencedToolCallingClient(
            [
                ToolCall(
                    name="query_metric",
                    arguments={
                        "metric_name": "avg_processing_days",
                        "group_by": ["determination__is_expedited"],
                        "filters": ["determination__is_expedited"],
                    },
                ),
                ToolCall(
                    name="query_metric",
                    arguments={
                        "metric_name": "avg_processing_days",
                        "group_by": ["determination__is_expedited"],
                    },
                ),
            ]
        )

        answer = service.ask(
            "What is the average processing time broken out by expedited status?",
            token,
            settings=probe_settings,
            llm_client=stub_llm,
        )

        assert answer.metric_names_used == ["avg_processing_days"]
        by_expedited = {
            row["determination__is_expedited"]: row["avg_processing_days"]
            for row in answer.result_rows
        }
        assert by_expedited == {True: 6.5, False: 25.0}
        assert len(stub_llm.seen_prompts) == 2
        assert "determination__is_expedited" in stub_llm.seen_prompts[1]

    def test_a_garbled_metric_name_triggers_a_corrective_retry_and_then_succeeds(
        self, probe_settings: Settings
    ) -> None:
        """A third real, observed failure mode (2026-08-25, live
        sampling): the model emitted a made-up compound expression
        ("determinations(is_expedited).avg_processing_days") instead of a
        real metric name. That's a pydantic ValidationError, not a
        MetricCompilationError -- it must still get the same one-shot
        corrective retry, carrying the validator's own "must be one of"
        list back to the model."""
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        stub_llm = _SequencedToolCallingClient(
            [
                ToolCall(
                    name="query_metric",
                    arguments={
                        "metric_name": "determinations(is_expedited).avg_processing_days",
                        "group_by": ["determination__is_expedited"],
                    },
                ),
                ToolCall(
                    name="query_metric",
                    arguments={
                        "metric_name": "avg_processing_days",
                        "group_by": ["determination__is_expedited"],
                    },
                ),
            ]
        )

        answer = service.ask(
            "What is the average processing time broken out by expedited status?",
            token,
            settings=probe_settings,
            llm_client=stub_llm,
        )

        assert answer.metric_names_used == ["avg_processing_days"]
        assert len(stub_llm.seen_prompts) == 2
        assert "not a known metric" in stub_llm.seen_prompts[1]

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
@pytest.mark.flaky(reruns=1)
class TestAskWithARealModel:
    """The one thing nothing above proves: that a real Ollama model,
    given the real role-scoped tool list, actually picks the right metric
    and dimension for a real natural-language question. Everything else
    about `ask()` (JWT handling, validation, execution, security) is
    already proven without a live model above.

    `reruns=1`, deliberately, and only here: `ask()`'s own bounded
    corrective retry (see `service.py`) already turns most real-model
    mistakes into a right answer within the request itself -- measured
    live (2026-08-25) at 9/10 correct end to end, up from 6/10 before that
    fix. The residual failure is `llama3.2:3b` picking a genuinely
    different wrong metric/dimension on *both* of its two tries within one
    request, which the request-level retry cannot help with by design (a
    third guess would be a retry-until-green loop, not a real second
    chance). A second, independent request -- which is what a CI rerun
    actually is -- gets a fresh sample from the same distribution, so it
    is a legitimate way to absorb that specific residual risk without
    weakening what a red run here still means: two full requests, each
    with its own two tries, both wrong, is still a real failure. This
    marker is deliberately scoped to this one class -- every other test in
    this project is either hermetic or already proven deterministic, and
    a rerun on any of them would just as deliberately hide a real bug."""

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
