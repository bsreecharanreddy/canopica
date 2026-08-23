"""Ingest -> dbt build -> serving materialization -> Metabase provisioning,
on an hourly schedule. Same four stages, same order, as `canopica_data.pipeline`
(what `make pipeline` runs by hand) -- this DAG calls the identical
underlying functions rather than duplicating their logic, so there is
exactly one implementation of each stage regardless of whether it's
triggered manually or on a schedule.

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


with DAG(
    dag_id="canopica_pipeline",
    description="Ingest -> dbt build -> serving materialization -> Metabase provisioning",
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
