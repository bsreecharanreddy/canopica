-- Runs once, on first container init (mounted into
-- /docker-entrypoint-initdb.d/) -- creates both databases and the
-- application role with the least privilege the app actually needs.
-- Operational schema migration is Flyway's job (run by api on
-- startup, Task 12); this script only creates the databases to migrate
-- into.
create role canopica_app with login password 'canopica_app';
create database canopica_operational owner canopica_app;
create database canopica_serving owner canopica_app;

-- pgmq (Phase 3 design doc §2.2): the queue mechanism decided since Phase
-- 1 but stood up for real only here. Created against the bootstrap
-- superuser role, same as this whole script, rather than as a Flyway
-- migration -- an extension install is infrastructure setup, not
-- canopica_operational's own application schema, and Flyway's
-- canopica_app role isn't guaranteed extension-creation privilege the
-- way this script's postgres role already has it. worker/'s own
-- queue.py never calls pgmq.create() itself; the two queues this phase
-- needs are created once, here, so both exist before anything tries to
-- send to them.
\connect canopica_operational
create extension if not exists pgmq cascade;
select pgmq.create('document_intake');
select pgmq.create('correspondence_dispatch');
-- The extension and both queues' tables above are owned by this script's
-- own bootstrap role (postgres), not canopica_app -- canopica_operational
-- being owned BY canopica_app doesn't extend to objects a different role
-- created inside it. Without these grants worker/ (which connects as
-- canopica_app, same as everything else) gets "permission denied for
-- schema pgmq" on every pgmq.* call -- caught by actually starting a
-- fresh container and querying as canopica_app, not assumed from
-- canopica_app owning the database.
grant usage on schema pgmq to canopica_app;
grant all on all tables in schema pgmq to canopica_app;
grant all on all sequences in schema pgmq to canopica_app;
grant execute on all functions in schema pgmq to canopica_app;
\connect postgres

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
