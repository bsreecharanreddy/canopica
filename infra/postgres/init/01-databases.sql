-- Runs once, on first container init (mounted into
-- /docker-entrypoint-initdb.d/) -- creates both databases and the
-- application role with the least privilege the app actually needs.
-- Operational schema migration is Flyway's job (run by portal-api on
-- startup, Task 12); this script only creates the databases to migrate
-- into.
create role ies_app with login password 'ies_app';
create database ies_operational owner ies_app;
create database ies_serving owner ies_app;

-- Airflow's own metadata DB (task/DAG-run state, connections, users) --
-- orchestration-internal, unrelated to the app's own operational data, so
-- it gets its own role rather than reusing ies_app (least privilege: an
-- Airflow credential compromise shouldn't also be an ies_operational one).
create role airflow with login password 'airflow';
create database airflow owner airflow;
