# The one-shot pipeline runner: ingestion -> dbt build -> serving
# materialization -> Metabase provisioning (canopica_data.pipeline). Built and
# run via the profile-gated `pipeline` Compose service; `uv sync` needs the
# project's own source present (uv_build installs it, not just its
# dependencies), so source is copied before syncing rather than after.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src src
RUN uv sync --frozen

COPY dbt dbt

# Phase 4 Task 9: dbt does not auto-install packages.yml's own
# dependencies (Elementary, now that Task 9 adds it) -- a bare `dbt
# build` fails outright ("found only 0 package(s) installed in
# dbt_packages") without this having run first. Baked in at image-build
# time, not runtime, since dbt_packages/ is gitignored and this container
# has no other reason to reach the network per invocation.
RUN uv run dbt deps --project-dir dbt/canopica_warehouse --profiles-dir dbt/canopica_warehouse

ENV CANOPICA_WAREHOUSE_ROOT=/app/warehouse
ENV CANOPICA_DUCKDB_PATH=/app/warehouse/canopica.duckdb

CMD ["uv", "run", "python", "-m", "canopica_data.pipeline"]
