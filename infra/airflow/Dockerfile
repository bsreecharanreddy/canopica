# Build context is data-platform/ (see docker-compose.yml's airflow
# services), not the repo root -- reuses that project's own .dockerignore
# (already correctly excludes .venv/warehouse/etc.) rather than needing a
# second one. LocalExecutor runs every task in-process in this one image,
# so ies_data's own runtime dependencies (the @task functions import it
# directly) need to be on it, not a second container.
#
# Airflow's own dependency graph is tightly pinned across ~100 transitive
# packages; ies_data's Python-importable dependencies are installed against
# Airflow's own published constraints file (Airflow's documented way to add
# custom dependencies to the image) rather than a bare `pip install`, which
# is a well-known way to break it. ies_data's own direct dependencies (the
# exact list in pyproject.toml's [project.dependencies], minus dbt-core/
# dbt-duckdb -- see below) are stripped out of that constraints file first:
# Airflow's constraints universe pins a version for every package any
# bundled provider's *optional* extras could ever need, and three of these
# conflicted outright when checked one at a time against a real
# ResolutionImpossible error, not guessed up front -- deltalake (Airflow
# constrains 0.24.0; ies_data needs >=1.6.2 for Task 10's bronze layer, a
# different major API generation, not just a newer patch), duckdb (1.1.3 vs
# >=1.5.5), httpx (0.27.0 vs >=0.28.1). None of these packages is something
# this image's Airflow core or its default (non-extra) providers actually
# import at runtime -- e.g. Airflow's own metadata-DB driver below is
# psycopg2, a different PyPI package from ies_data's psycopg (v3) -- so
# excluding the rest of the list pre-emptively rather than waiting to hit
# each one costs nothing real. Everything else in the file stays constrained.
#
# dbt-core is handled separately, in its own venv, not installed into this
# shared environment at all: dbt-core>=1.12.3 requires click>=8.3, which
# genuinely conflicts with Airflow 2.10.5's own click==8.1.8 (Airflow's CLI
# depends on it directly -- this one is a real incompatibility, not
# incidental constraint-file noise). dbt only ever runs as a subprocess CLI
# in this codebase (see ies_data.pipeline's own subprocess.run(["dbt",
# "build", ...]) -- what `make pipeline` already does) -- never imported as
# a Python module -- so it has no need to share Airflow's environment or
# its click version at all.
FROM apache/airflow:2.10.5-python3.12

# /opt is root-owned by default -- airflow (non-root, the image's own
# convention) can't create new directories there without this. COPY's own
# --chown handles /opt/ies-data-platform's *contents* fine regardless of
# current user, but the plain `python -m venv` RUN step below needs the
# directory to already exist and be writable.
USER root
RUN mkdir -p /opt/ies-data-platform /opt/dbt-venv \
    && chown airflow:root /opt/ies-data-platform /opt/dbt-venv
USER airflow

COPY --chown=airflow:root pyproject.toml README.md /opt/ies-data-platform/
COPY --chown=airflow:root src /opt/ies-data-platform/src
RUN curl -sSL "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt" \
        | grep -vE '^(connectorx|deltalake|duckdb|httpx|numpy|polars|psycopg|pyarrow|pydantic|pydantic_core|pydantic-settings|typing_extensions)==' \
        > /tmp/constraints.txt \
    && pip install --no-cache-dir --no-deps /opt/ies-data-platform \
    && pip install --no-cache-dir --constraint /tmp/constraints.txt \
        "connectorx>=0.4.5" "deltalake>=1.6.2" "duckdb>=1.5.5" "httpx>=0.28.1" \
        "numpy>=2.5.2" "polars>=1.43.2" "psycopg[binary]>=3.3.4" "pyarrow>=25.0.1" \
        "pydantic>=2.13.4" "pydantic-settings>=2.15.0" \
    && rm /tmp/constraints.txt

# dbt's own fully isolated venv -- see the block comment above. The
# dbt_build BashOperator in ies_pipeline_dag.py calls this venv's dbt
# binary by absolute path, not a bare `dbt` relying on PATH resolution
# (which would otherwise still find Airflow's own environment first).
COPY --chown=airflow:root dbt /opt/ies-data-platform/dbt
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core>=1.12.3" "dbt-duckdb>=1.11.0"

# Matches data-platform/Dockerfile's own two env vars: IES_WAREHOUSE_ROOT is
# what Settings.warehouse_root/bronze_root/duckdb_path derive from (config.py),
# IES_DUCKDB_PATH is what dbt's profiles.yml reads directly via env_var() --
# two names for the same file because two different tools each already read
# a different one; keeping both here keeps this image consistent with the
# same two-env-var contract the pipeline image already uses.
ENV IES_WAREHOUSE_ROOT=/opt/ies-data-platform/warehouse
ENV IES_DUCKDB_PATH=/opt/ies-data-platform/warehouse/ies.duckdb
