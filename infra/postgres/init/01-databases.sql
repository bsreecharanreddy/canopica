-- Runs once, on first container init (mounted into
-- /docker-entrypoint-initdb.d/) -- creates both databases and the
-- application role with the least privilege the app actually needs.
-- Operational schema migration is Flyway's job (run by portal-api on
-- startup, Task 12); this script only creates the databases to migrate
-- into.
create role canopica_app with login password 'canopica_app';
create database canopica_operational owner canopica_app;
create database canopica_serving owner canopica_app;
