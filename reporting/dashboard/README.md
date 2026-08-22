# Metabase dashboard

Metabase is provisioned entirely from code -- no manual click-through setup
-- by `canopica_data.reporting.provision_metabase`. Run it against a running
Metabase instance pointed at the serving Postgres database:

```bash
cd data-platform
uv run python -m canopica_data.reporting.provision_metabase
```

Credentials and the target URL come from `CANOPICA_METABASE_URL`,
`CANOPICA_METABASE_USER`, and `CANOPICA_METABASE_PASSWORD` (local-dev defaults in
`infra/.env.example` and in `Settings` itself -- see
`data-platform/src/canopica_data/config.py`). The script:

1. Completes Metabase's one-time initial-admin setup if it hasn't run yet
   (checked via `/api/session/properties`'s `has-user-setup` field),
   otherwise logs in with the existing admin account.
2. Creates (or finds, by name) a Postgres database connection named
   "Canopica Serving" pointing at `CANOPICA_SERVING_DSN`.
3. Creates (or finds) a native SQL question, "Determinations by month and
   outcome", over `reporting.mart_determination_outcomes`.
4. Creates (or finds) a dashboard, "SNAP determinations", and adds the
   question to it.

Every step is idempotent by name -- re-running the script (e.g. as part of
`make pipeline`, once Task 12 wires that up) finds and reuses each object
instead of duplicating it. This was verified for real during development:
run once against a freshly-created Metabase container (exercising the
initial-setup path), then run again (exercising the login + find-existing
path) -- the database/card/dashboard counts by name stayed at exactly one
each across both runs.

## Result

![SNAP determinations dashboard](./snap-determinations-dashboard.png)

Captured against a real, freshly-provisioned Metabase instance connected to
a seeded serving database -- not a mockup. The dashboard's single card is a
native query directly against `reporting.mart_determination_outcomes`; what
it shows is exactly what `materialize_gold()` last wrote there, nothing
re-derived.

## `CANOPICA_SERVING_DSN`'s host must resolve for Metabase, not for the caller

`provision_metabase.py` never opens a database connection itself -- it only
sends `CANOPICA_SERVING_DSN`'s host/port/dbname/user/password to Metabase's own
`/api/database` endpoint, and it's *Metabase's container* that has to
resolve that host, not whatever shell or container runs
`provision_metabase.py`. Found running this for real against the Task 11
Compose slice (`infra/docker-compose.yml`'s `postgres` + `metabase`
services): invoking the script from the host machine with
`CANOPICA_SERVING_DSN=...@localhost:5432/...` (correct for a host process
reaching Postgres through its published port) made Metabase itself try to
resolve `localhost` from *inside its own container* and fail with a 400 --
`localhost` inside the metabase container is the metabase container, not
the postgres one. Fixed by pointing at the Compose service name instead:
`CANOPICA_SERVING_DSN=postgresql://canopica_app:canopica_app@postgres:5432/canopica_serving`,
resolvable by any container on the same Compose network via Docker's
embedded DNS.

This isn't a problem in the real pipeline: Task 12's one-shot `pipeline`
container runs `extract_to_bronze` → `dbt build` → `materialize_gold` →
`provision_metabase` all inside the same Compose network as `postgres` and
`metabase`, so one `CANOPICA_SERVING_DSN` value (the `postgres` service name)
resolves correctly for every step, including the parts `materialize_gold`
itself runs from inside that same container. It only bit here because this
task's manual verification ran the script from the host, ahead of Task 12
giving `pipeline` a container to run in.

## API version note

`provision_metabase.py`'s request shapes (the `/api/setup` body, the
`PUT /api/dashboard/:id` `dashcards` shape, etc.) were verified against a
live `metabase/metabase:latest` container (v0.63.14.2) during development,
not written from documentation alone -- Metabase's REST API isn't fully
documented and has changed shape across versions (the dashboard-card
attachment endpoint in particular). If a future Metabase upgrade breaks
this script, re-verify each call against `/api/docs` on the new version
rather than assuming the old shapes still hold.
