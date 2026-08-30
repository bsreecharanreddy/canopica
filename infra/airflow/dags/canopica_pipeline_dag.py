"""Ingest -> dbt build -> serving materialization -> Metabase provisioning,
on an hourly schedule. Same four stages, same order, as `canopica_data.pipeline`
(what `make pipeline` runs by hand) -- this DAG calls the identical
underlying functions rather than duplicating their logic, so there is
exactly one implementation of each stage regardless of whether it's
triggered manually or on a schedule. Phase 4 Task 4 adds a fifth,
independent task on the same hourly cadence: `run_qc_sample`, which
triggers the QC / Payment Error Rate Assistant's sampled re-derivation.

Imports from `canopica_data` happen inside each task function, not at module
level -- the scheduler re-parses every DAG file on its own file-processing
interval just to discover DAG structure, and importing dbt-core/polars/
connectorx (all fairly heavy) at module level would slow that down for no
benefit, since parsing never needs the task bodies themselves. Airflow's
own top-level-code performance guidance recommends exactly this.
"""

from __future__ import annotations

import sys

import pendulum
from airflow.decorators import task
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator

DBT_PROJECT_DIR = "/opt/canopica-data-platform/dbt/canopica_warehouse"
# dbt lives in its own venv, isolated from Airflow's own click version --
# see infra/airflow/Dockerfile's block comment for why. Called by absolute
# path so this resolves to that venv's dbt, not a same-named binary
# anywhere else on PATH.
DBT_BIN = "/opt/dbt-venv/bin/dbt"

# Container-network addresses (this DAG runs inside the airflow-scheduler
# service) -- same split api's own docker-compose.yml environment block
# already documents for its own Keycloak jwks-uri: a hardcoded address for
# a same-Compose-network peer, not a configurable setting, matching how
# DBT_PROJECT_DIR/DBT_BIN above are already plain module constants rather
# than env-driven config.
API_BASE_URL = "http://api:8080"
KEYCLOAK_TOKEN_URL = "http://keycloak:8080/realms/canopica-workers/protocol/openid-connect/token"


@task(task_id="extract")
def extract() -> None:
    from canopica_data.config import Settings
    from canopica_data.ingestion.extract import ALL_TABLES, extract_to_bronze

    settings = Settings()
    counts = extract_to_bronze(settings.operational_dsn, settings.bronze_root, list(ALL_TABLES))
    for table, count in counts.items():
        print(f"ingested {table}: {count} rows", file=sys.stderr)


@task(task_id="tokenize")
def tokenize() -> None:
    from canopica_data.config import Settings
    from canopica_data.governance.tokenize import tokenize_person_names

    settings = Settings()
    token_count = tokenize_person_names(
        settings.operational_dsn, settings.bronze_root, settings.pii_encryption_key
    )
    print(f"tokenized {token_count} person names", file=sys.stderr)


@task(task_id="materialize")
def materialize() -> None:
    from canopica_data.config import Settings
    from canopica_data.serving.materialize import materialize_gold

    settings = Settings()
    mart_counts = materialize_gold(settings.duckdb_path, settings.serving_dsn)
    for mart, count in mart_counts.items():
        print(f"materialized {mart}: {count} rows", file=sys.stderr)


@task(task_id="provision_metabase")
def provision_metabase() -> None:
    from canopica_data.config import Settings
    from canopica_data.reporting.provision_metabase import provision

    dashboard_id = provision(Settings())
    print(f"Metabase dashboard ready: {dashboard_id}", file=sys.stderr)


@task(task_id="run_qc_sample")
def run_qc_sample() -> None:
    """Phase 4 Task 4: triggers QcSamplingService's own sampled re-derivation via the internal,
    ADMIN-scoped /api/internal/qc/run-sample endpoint -- the same "no new DMN-evaluation code, just a
    new caller" reasoning QcSamplingService's own doc comment gives applies here too: this task is a
    caller, not a reimplementation. Authenticates as canopica-airflow, a real client_credentials
    service-account client (identity/realm-export/canopica-workers-realm.json) -- deliberately not
    test-worker's own password grant, which that client's own name/description reserve for pytest/
    Maven test suites, never a real scheduled caller. Runs independently of the extract/dbt/materialize
    chain above -- it writes to the operational database directly (through the API), not the warehouse,
    so it has nothing to wait on and nothing waits on it; the next hourly dbt_build/materialize picks up
    whatever it sampled this run or the run after."""
    import httpx

    with httpx.Client(timeout=30.0) as client:
        token_response = client.post(
            KEYCLOAK_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": "canopica-airflow",
                "client_secret": "canopica-airflow-secret",
            },
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]

        response = client.post(
            f"{API_BASE_URL}/api/internal/qc/run-sample",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        body = response.json()
    print(f"QC sample run: {body['sampled']} sampled, {body['flagged']} flagged", file=sys.stderr)


with DAG(
    dag_id="canopica_pipeline",
    description="Ingest -> dbt build -> serving materialization -> Metabase provisioning; QC sampling",
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["canopica"],
) as dag:
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"{DBT_BIN} build --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROJECT_DIR} --target local"
        ),
    )

    extract() >> tokenize() >> dbt_build >> materialize() >> provision_metabase()

    # Independent of the chain above -- run_qc_sample writes to the operational database directly
    # (through the API), not the warehouse, so it has nothing to wait on and nothing waits on it.
    run_qc_sample()
