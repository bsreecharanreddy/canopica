"""SOP Process-Improvement Mining (Phase 4 Task 8, design doc §2.6).

`TestGroundingErrors`/`TestDraftNarrativeGuardRails`/
`TestDraftGroundedNarrative` are pure unit tests, no I/O -- same shape
`test_sla_monitor.py`'s own grounding-check tests take for a different
capability. `TestMineProcessImprovements` proves the orchestration wiring
(tool-call -> ask() -> grounded narrative) against the same tiny,
hand-built known-answer DuckDB warehouse `test_analytics_copilot.py`'s own
`probe_settings` uses, rebuilt locally here rather than imported across
test modules (each dbt/analytics test file in this repo builds its own
fixture rather than sharing one via conftest.py) -- this keeps the new
metrics Task 8 itself added (rejected_determinations, notice_rejection_
rate) out of scope for this file entirely: those are already proven to
compile and compute correctly against a real dbt-built warehouse by
`data-platform/tests/test_metric_semantics.py`, so this file only needs
to exercise `avg_processing_days`, already known-answer here.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import duckdb
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel

from canopica_ai.analytics_copilot import service
from canopica_ai.analytics_copilot.jwt_auth import WorkerClaims
from canopica_ai.analytics_copilot.mining import (
    MiningLlmClient,
    NarrativeDraftError,
    NarrativeGroundingError,
    draft_grounded_narrative,
    draft_narrative,
    grounding_errors,
    mine_process_improvements,
)
from canopica_ai.analytics_copilot.service import AnalyticsAnswer
from canopica_ai.common.llm_client import LlmResponse, ToolCall, ToolSpec
from canopica_ai.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PLATFORM_ROOT = REPO_ROOT / "data-platform"
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"
DBT_BINARY = DATA_PLATFORM_ROOT / ".venv" / "bin" / "dbt"


def _rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _worker_jwt(private_key: rsa.RSAPrivateKey, *, roles: list[str]) -> str:
    return jwt.encode(
        {"sub": "fixture-worker", "realm_access": {"roles": roles}}, private_key, algorithm="RS256"
    )


def _answer(**overrides: object) -> AnalyticsAnswer:
    defaults: dict[str, object] = {
        "compiled_sql": "select 1",
        "result_rows": [
            {"determination__is_expedited": True, "avg_processing_days": 6.5},
            {"determination__is_expedited": False, "avg_processing_days": 25.0},
        ],
        "metric_names_used": ["avg_processing_days"],
    }
    defaults.update(overrides)
    return AnalyticsAnswer(**defaults)  # type: ignore[arg-type]


class _StubNarrativeClient:
    """`responses` items are canned JSON strings; an `Exception` instance
    stands in for a real transient failure, same convention
    `test_sla_monitor.py`'s own `_StubReasonClient` uses."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses: list[str | Exception] = list(responses)

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        next_response = self._responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return LlmResponse(text=next_response)


def _narrative_json(narrative: str) -> str:
    return json.dumps({"narrative": narrative})


class TestGroundingErrors:
    def test_a_narrative_using_only_real_returned_numbers_passes(self) -> None:
        errors = grounding_errors(
            "Expedited cases average 6.5 days versus 25 for standard cases.", _answer()
        )
        assert errors == []

    def test_an_invented_number_is_caught(self) -> None:
        errors = grounding_errors("Processing takes an average of 42 days.", _answer())
        assert len(errors) == 1
        assert "42" in errors[0]

    def test_a_ratio_metric_is_grounded_against_its_percentage_form(self) -> None:
        # notice_rejection_rate (Task 8's own new ratio metric) returns a
        # fraction (e.g. 0.3333) -- a narrative is near-certain to phrase
        # that as "33%", not "0.3333", so the percentage-scaled form must
        # ground too, not just the raw fraction.
        answer = _answer(
            result_rows=[{"notice_rejection_rate": 0.3333}],
            metric_names_used=["notice_rejection_rate"],
        )
        errors = grounding_errors("About 33% of reviewed notices were rejected.", answer)
        assert errors == []


class TestDraftNarrativeGuardRails:
    def test_a_valid_response_becomes_the_narrative(self) -> None:
        narrative = draft_narrative(
            "how is processing time trending?",
            _answer(),
            llm_client=_StubNarrativeClient([_narrative_json("Real narrative.")]),
        )
        assert narrative == "Real narrative."

    def test_a_malformed_response_is_retried_once(self) -> None:
        narrative = draft_narrative(
            "how is processing time trending?",
            _answer(),
            llm_client=_StubNarrativeClient(["not valid json", _narrative_json("Real narrative.")]),
        )
        assert narrative == "Real narrative."

    def test_two_consecutive_malformed_responses_raise(self) -> None:
        with pytest.raises(NarrativeDraftError):
            draft_narrative(
                "how is processing time trending?",
                _answer(),
                llm_client=_StubNarrativeClient(["not valid json", "still not valid json"]),
            )


class TestDraftGroundedNarrative:
    def test_an_ungrounded_response_is_retried_then_raises(self) -> None:
        ungrounded = _narrative_json("Processing takes an average of 42 days.")
        with pytest.raises(NarrativeGroundingError):
            draft_grounded_narrative(
                "how is processing time trending?",
                _answer(),
                llm_client=_StubNarrativeClient([ungrounded, ungrounded]),
            )

    def test_a_grounded_retry_after_an_ungrounded_first_attempt_succeeds(self) -> None:
        narrative = draft_grounded_narrative(
            "how is processing time trending?",
            _answer(),
            llm_client=_StubNarrativeClient(
                [
                    _narrative_json("Processing takes an average of 42 days."),
                    _narrative_json("Expedited cases average 6.5 days."),
                ]
            ),
        )
        assert narrative == "Expedited cases average 6.5 days."


def _build_probe_warehouse(tmp_path: Path) -> Settings:
    """Same known-answer fixture `test_analytics_copilot.py`'s own
    `probe_settings` builds -- rebuilt locally rather than shared across
    test modules (see this file's own module docstring)."""
    duckdb_path = tmp_path / "probe.duckdb"
    connection = duckdb.connect(str(duckdb_path))
    connection.execute("CREATE SCHEMA main_gold")
    connection.execute(
        """
        CREATE TABLE main_gold.mart_processing_timeliness (
            determination_key BIGINT,
            program_request_key BIGINT,
            program_code VARCHAR,
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
        (1, 1, 'SNAP', true,  '2026-01-01', '2026-01-04', 3,  7,  false),
        (2, 2, 'SNAP', true,  '2026-01-01', '2026-01-11', 10, 7,  true),
        (3, 3, 'SNAP', false, '2026-01-01', '2026-01-16', 15, 30, false),
        (4, 4, 'SNAP', false, '2026-01-01', '2026-02-05', 35, 30, true)
        """
    )
    connection.close()

    settings = Settings(
        data_platform_dbt_project_dir=DBT_PROJECT_DIR,
        mf_binary_path=DATA_PLATFORM_ROOT / ".venv" / "bin" / "mf",
        duckdb_path=duckdb_path,
    )

    # See test_analytics_copilot.py's own identical step for why this is
    # needed: dbt does not auto-install packages.yml's own dependencies.
    deps = subprocess.run(
        [str(DBT_BINARY), "deps", "--project-dir", str(DBT_PROJECT_DIR),
         "--profiles-dir", str(DBT_PROJECT_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert deps.returncode == 0, deps.stdout + deps.stderr

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


@pytest.fixture(scope="module")
def probe_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    return _build_probe_warehouse(tmp_path_factory.mktemp("mining_probe"))


class _CombinedStubClient:
    """Implements both halves of `MiningLlmClient` -- `generate_tool_call`
    for `ask()`'s own tool-selection step, `generate_structured` for the
    narrative step -- so `mine_process_improvements` never touches a real
    Ollama instance in this test."""

    def __init__(self, call: ToolCall, narrative_responses: list[str]) -> None:
        self._call = call
        self._narrative_client = _StubNarrativeClient(list(narrative_responses))

    def generate_tool_call(self, prompt: str, tools: Sequence[ToolSpec]) -> ToolCall:
        return self._call

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        return self._narrative_client.generate_structured(prompt, schema)


class TestMineProcessImprovements:
    @pytest.fixture(autouse=True)
    def _stub_jwt_decoding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_decode(token: str, *, settings: Settings) -> WorkerClaims:
            payload = jwt.decode(token, options={"verify_signature": False})
            return WorkerClaims(
                subject=payload["sub"],
                roles=frozenset(payload.get("realm_access", {}).get("roles", [])),
            )

        monkeypatch.setattr(service, "decode_worker_token", fake_decode)

    def test_the_narrative_is_grounded_in_the_real_query_result(
        self, probe_settings: Settings
    ) -> None:
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        stub_llm: MiningLlmClient = _CombinedStubClient(
            ToolCall(
                name="query_metric",
                arguments={
                    "metric_name": "avg_processing_days",
                    "group_by": ["determination__is_expedited"],
                },
            ),
            [_narrative_json("Expedited cases average 6.5 days versus 25 for standard cases.")],
        )

        answer = mine_process_improvements(
            "how does processing time differ by expedited status?",
            token,
            settings=probe_settings,
            llm_client=stub_llm,
        )

        assert answer.metric_names_used == ["avg_processing_days"]
        assert answer.narrative == "Expedited cases average 6.5 days versus 25 for standard cases."

    def test_an_ungrounded_narrative_raises_rather_than_returning_an_invented_figure(
        self, probe_settings: Settings
    ) -> None:
        private_key, _ = _rsa_keypair()
        token = _worker_jwt(private_key, roles=["WORKER"])
        ungrounded = _narrative_json("Processing takes an average of 42 days.")
        stub_llm: MiningLlmClient = _CombinedStubClient(
            ToolCall(
                name="query_metric",
                arguments={
                    "metric_name": "avg_processing_days",
                    "group_by": ["determination__is_expedited"],
                },
            ),
            [ungrounded, ungrounded],
        )

        with pytest.raises(NarrativeGroundingError):
            mine_process_improvements(
                "how does processing time differ by expedited status?",
                token,
                settings=probe_settings,
                llm_client=stub_llm,
            )
