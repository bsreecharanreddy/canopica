"""Triggers a real run of the ies_pipeline DAG through Airflow's own REST
API against the live Compose stack and asserts it completes -- proves the
DAG is wired correctly (imports, task dependencies, the real ies_data/dbt
calls each task makes) end to end, not just that the file parses cleanly."""

import time

import httpx
import psycopg
import pytest

AIRFLOW_URL = "http://localhost:8082"
AUTH = ("admin", "IesAirflowAdmin123!")
DAG_ID = "ies_pipeline"

OPERATIONAL_DSN = "postgresql://ies_app:ies_app@localhost:5432/ies_operational"
SERVING_DSN = "postgresql://ies_app:ies_app@localhost:5432/ies_serving"


@pytest.mark.e2e
def test_ies_pipeline_dag_runs_to_completion_and_materializes_the_current_data() -> None:
    with httpx.Client(base_url=AIRFLOW_URL, auth=AUTH, timeout=30) as client:
        # Starts unpaused (AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=false, see
        # infra/docker-compose.yml) so its own @hourly schedule actually fires --
        # this call only guards against that env var ever changing out from
        # under the test, it isn't what makes the schedule itself work.
        client.patch(f"/api/v1/dags/{DAG_ID}", json={"is_paused": False}).raise_for_status()

        trigger = client.post(f"/api/v1/dags/{DAG_ID}/dagRuns", json={})
        trigger.raise_for_status()
        dag_run_id = trigger.json()["dag_run_id"]

        state = "queued"
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline and state not in ("success", "failed"):
            time.sleep(5)
            run = client.get(f"/api/v1/dags/{DAG_ID}/dagRuns/{dag_run_id}")
            run.raise_for_status()
            state = run.json()["state"]

        assert state == "success", f"DAG run {dag_run_id} ended in {state!r}, expected success"

    # Order-independent on purpose: this test may run before or after
    # test_end_to_end.py has created any real determinations (pytest's
    # default collection order isn't something to depend on), so the
    # meaningful assertion isn't a specific row count -- it's that the
    # materialize stage genuinely rebuilt the mart from *this run's* real
    # operational state, the same "the dashboard's number is the rules
    # engine's own number, not a re-derivation" property test_materialize.py
    # already proves at the function level, re-checked here against the
    # live stack the DAG (not a direct function call) actually touched.
    with psycopg.connect(OPERATIONAL_DSN) as conn:
        operational_row = conn.execute("select count(*) from eligibility_determination").fetchone()
    assert operational_row is not None
    operational_count = operational_row[0]

    with psycopg.connect(SERVING_DSN) as conn:
        mart_row = conn.execute(
            "select coalesce(sum(determination_count), 0) "
            "from reporting.mart_determination_outcomes"
        ).fetchone()
    assert mart_row is not None
    mart_total = mart_row[0]

    assert mart_total == operational_count
