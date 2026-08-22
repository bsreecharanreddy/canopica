"""The one-shot pipeline: ingest operational tables to bronze, build the
dbt warehouse (silver + gold), materialize gold into the serving database,
then provision Metabase against it. This is what the `pipeline` Compose
service (profile-gated, see infra/docker-compose.yml) runs as its sole
command, and what `make pipeline` invokes.

uv run python -m canopica_data.pipeline
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from canopica_data.config import Settings
from canopica_data.ingestion.extract import ALL_TABLES, extract_to_bronze
from canopica_data.reporting.provision_metabase import provision
from canopica_data.serving.materialize import materialize_gold

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"


def main() -> None:
    settings = Settings()

    counts = extract_to_bronze(settings.operational_dsn, settings.bronze_root, list(ALL_TABLES))
    for table, count in counts.items():
        print(f"ingested {table}: {count} rows", file=sys.stderr)

    # Inherits the process's own environment, which already carries
    # CANOPICA_WAREHOUSE_ROOT/CANOPICA_DUCKDB_PATH -- the same two env vars
    # profiles.yml's env_var() calls read, and the same ones Settings
    # derives warehouse_root/duckdb_path from, so one set of container env
    # vars keeps dbt and this module pointed at the same warehouse file.
    subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            str(DBT_PROJECT_DIR),
            "--target",
            "local",
        ],
        cwd=DATA_PLATFORM_ROOT,
        check=True,
    )

    mart_counts = materialize_gold(settings.duckdb_path, settings.serving_dsn)
    for mart, count in mart_counts.items():
        print(f"materialized {mart}: {count} rows", file=sys.stderr)

    dashboard_id = provision(settings)
    print(f"Metabase dashboard ready: {dashboard_id}", file=sys.stderr)


if __name__ == "__main__":
    main()
