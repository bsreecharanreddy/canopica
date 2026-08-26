-- Runs once, on first container init (mounted into
-- /docker-entrypoint-initdb.d/) -- creates both databases and the
-- application role with the least privilege the app actually needs.
-- Operational schema migration is Flyway's job (run by api on
-- startup, Task 12); this script only creates the databases to migrate
-- into.
create role canopica_app with login password 'canopica_app';
create database canopica_operational owner canopica_app;
create database canopica_serving owner canopica_app;

-- Airflow's own metadata DB (task/DAG-run state, connections, users) --
-- orchestration-internal, unrelated to the app's own operational data, so
-- it gets its own role rather than reusing canopica_app (least privilege: an
-- Airflow credential compromise shouldn't also be a canopica_operational one).
create role airflow with login password 'airflow';
create database airflow owner airflow;

-- Guards the Postgres *serving* layer (Metabase, Power BI/TMDL) that reads
-- canopica_serving.reporting.* -- not the Analytics Copilot, which queries
-- DuckDB directly and is backstopped by DuckDB session settings instead
-- (Phase 2 Task 4 design doc: 2026-08-24-analytics-semantic-layer-
-- execution-and-authorization.md). materialize_gold() (re)creates every
-- reporting.* table on each pipeline run as canopica_app; default privileges
-- make every future materialization grant select automatically, without
-- touching materialize.py itself.
create role canopica_analytics_ro with login password 'canopica_analytics_ro';
grant connect on database canopica_serving to canopica_analytics_ro;
-- Postgres grants CONNECT on every database to PUBLIC by default -- found
-- by actually testing this role against canopica_operational, not assumed.
-- Without this, the role could connect to the PII-bearing operational
-- database (no table grants there, but connecting at all is unnecessary
-- exposure for a role whose entire purpose is read-only reporting access).
revoke connect on database canopica_operational from public;
\connect canopica_serving
create schema if not exists reporting authorization canopica_app;
grant usage on schema reporting to canopica_analytics_ro;
alter default privileges for role canopica_app in schema reporting
    grant select on tables to canopica_analytics_ro;
