"""A real API request and a real pipeline stage each produce a trace
Jaeger's own query API can find -- the same "verify against the real
thing" standard as test_stack_smoke.py's endpoint checks, not a mock.

Needs the full stack already up (`make up`), same precondition as every
other `e2e`-marked test in this suite.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from canopica_data.config import Settings
from canopica_data.ingestion.extract import extract_to_bronze
from canopica_data.synthetic.generator import generate_households
from canopica_data.synthetic.loader import post_households

JAEGER_QUERY_URL = "http://localhost:16686"


def _wait_for_trace(service: str, *, deadline_seconds: float = 20.0) -> None:
    """Jaeger's own indexing lags a real span's export by a second or two --
    poll rather than asserting on the first response, the same shape as
    test_airflow_dag.py's own dag-run-state poll."""
    deadline = time.monotonic() + deadline_seconds
    last_body: object = None
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{JAEGER_QUERY_URL}/api/traces", params={"service": service, "limit": 20}, timeout=10
        )
        response.raise_for_status()
        body = response.json()
        last_body = body
        if body["data"]:
            return
        time.sleep(1)
    pytest.fail(f"no trace found for service={service!r} within {deadline_seconds}s: {last_body}")


@pytest.mark.e2e
def test_a_real_api_request_produces_a_trace_in_jaeger() -> None:
    household = generate_households(1, seed=9001)[0]
    post_households([household], "http://localhost:8080")

    _wait_for_trace("canopica-api")


@pytest.mark.e2e
def test_a_real_pipeline_stage_produces_a_trace_in_jaeger(tmp_path: Path) -> None:
    settings = Settings()
    extract_to_bronze(settings.operational_dsn, tmp_path / "bronze", ["person"])

    _wait_for_trace("canopica-data-platform")
