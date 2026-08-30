# Build context is the repo root (docker-compose.yml's x-airflow-common),
# not data-platform/ alone as it was before Phase 4 Task 6 -- this image
# now needs to COPY from both data-platform/ and ai/ (see the root
# .dockerignore's own header comment for why both are reachable from
# here). LocalExecutor runs every task in-process in this one image, so
# canopica_data's own runtime dependencies (the @task functions import it
# directly) need to be on it, not a second container.
#
# Airflow's own dependency graph is tightly pinned across ~100 transitive
# packages; canopica_data's Python-importable dependencies are installed against
# Airflow's own published constraints file (Airflow's documented way to add
# custom dependencies to the image) rather than a bare `pip install`, which
# is a well-known way to break it. canopica_data's own direct dependencies (the
# exact list in pyproject.toml's [project.dependencies], minus dbt-core/
# dbt-duckdb -- see below) are stripped out of that constraints file first:
# Airflow's constraints universe pins a version for every package any
# bundled provider's *optional* extras could ever need, and three of these
# conflicted outright when checked one at a time against a real
# ResolutionImpossible error, not guessed up front -- deltalake (Airflow
# constrains 0.24.0; canopica_data needs >=1.6.2 for Task 10's bronze layer, a
# different major API generation, not just a newer patch), duckdb (1.1.3 vs
# >=1.5.5), httpx (0.27.0 vs >=0.28.1). None of these packages is something
# this image's Airflow core or its default (non-extra) providers actually
# import at runtime -- e.g. Airflow's own metadata-DB driver below is
# psycopg2, a different PyPI package from canopica_data's psycopg (v3) -- so
# excluding the rest of the list pre-emptively rather than waiting to hit
# each one costs nothing real. Everything else in the file stays constrained.
#
# dbt-core and ai/ (canopica-ai) are both handled the same way as each
# other, and differently from canopica_data above: each gets its own fully
# isolated venv, never merged into this shared, constraint-pinned
# environment. dbt-core>=1.12.3 requires click>=8.3, which genuinely
# conflicts with Airflow 2.10.5's own click==8.1.8 (Airflow's CLI depends
# on it directly). ai/ is different -- Phase 4 Task 6 is its first Airflow
# call site, and nothing has actually proven canopica-ai's own much wider
# dependency set (boto3, deepeval, fastapi, mcp, opensearch-py,
# scikit-learn, uvicorn, on top of the same connectorx/duckdb/httpx/
# psycopg/pydantic canopica_data already needed stripped from the
# constraints file above) is conflict-free against Airflow's own -- and
# `infra/fly/Dockerfile.public-demo` (Task 9 Step 5) already proves the
# opposite is trivially true: `uv sync --frozen --no-dev` against ai/'s
# own committed `uv.lock`, in total isolation, installs cleanly with zero
# conflict-resolution work, because there's no shared environment to
# conflict *with*. Reusing that exact approach here costs nothing and
# avoids repeating the multi-package elimination work canopica_data's own
# entry above needed. Both isolated tools are called the same way:
# `dbt_build`/`refresh_sla_stall_reasons` in canopica_pipeline_dag.py are
# BashOperators invoking each venv's own binary by absolute path, never a
# bare command relying on PATH resolution (which would otherwise still
# find Airflow's own environment first).
FROM apache/airflow:2.10.5-python3.12

# /opt is root-owned by default -- airflow (non-root, the image's own
# convention) can't create new directories there without this. COPY's own
# --chown handles /opt/canopica-data-platform's *contents* fine regardless of
# current user, but the plain `python -m venv` RUN step below needs the
# directory to already exist and be writable.
USER root
RUN mkdir -p /opt/canopica-data-platform /opt/dbt-venv /opt/canopica-ai \
    && chown airflow:root /opt/canopica-data-platform /opt/dbt-venv /opt/canopica-ai
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /usr/local/bin/
USER airflow

COPY --chown=airflow:root data-platform/pyproject.toml data-platform/README.md /opt/canopica-data-platform/
COPY --chown=airflow:root data-platform/src /opt/canopica-data-platform/src
RUN curl -sSL "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt" \
        | grep -vE '^(connectorx|deltalake|duckdb|httpx|numpy|polars|psycopg|pyarrow|pydantic|pydantic_core|pydantic-settings|typing_extensions)==' \
        > /tmp/constraints.txt \
    && pip install --no-cache-dir --no-deps /opt/canopica-data-platform \
    && pip install --no-cache-dir --constraint /tmp/constraints.txt \
        "connectorx>=0.4.5" "deltalake>=1.6.2" "duckdb>=1.5.5" "httpx>=0.28.1" \
        "numpy>=2.5.2" "polars>=1.43.2" "psycopg[binary]>=3.3.4" "pyarrow>=25.0.1" \
        "pydantic>=2.13.4" "pydantic-settings>=2.15.0" \
    && rm /tmp/constraints.txt

# dbt's own fully isolated venv -- see the block comment above. The
# dbt_build BashOperator in canopica_pipeline_dag.py calls this venv's dbt
# binary by absolute path, not a bare `dbt` relying on PATH resolution
# (which would otherwise still find Airflow's own environment first).
COPY --chown=airflow:root data-platform/dbt /opt/canopica-data-platform/dbt
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core>=1.12.3" "dbt-duckdb>=1.11.0"

# ai/'s own fully isolated venv -- see the block comment above. Frozen
# against the real committed lockfile (`--frozen`), the same reproducible
# install `infra/fly/Dockerfile.public-demo` already relies on; `--no-dev`
# skips ai/'s own test/lint tooling, which this image never runs.
COPY --chown=airflow:root ai/pyproject.toml ai/uv.lock ai/README.md /opt/canopica-ai/
COPY --chown=airflow:root ai/src /opt/canopica-ai/src
RUN cd /opt/canopica-ai && uv python install 3.12 && uv sync --frozen --no-dev

# Matches data-platform/Dockerfile's own two env vars: CANOPICA_WAREHOUSE_ROOT is
# what Settings.warehouse_root/bronze_root/duckdb_path derive from (config.py),
# CANOPICA_DUCKDB_PATH is what dbt's profiles.yml reads directly via env_var() --
# two names for the same file because two different tools each already read
# a different one; keeping both here keeps this image consistent with the
# same two-env-var contract the pipeline image already uses.
ENV CANOPICA_WAREHOUSE_ROOT=/opt/canopica-data-platform/warehouse
ENV CANOPICA_DUCKDB_PATH=/opt/canopica-data-platform/warehouse/canopica.duckdb
