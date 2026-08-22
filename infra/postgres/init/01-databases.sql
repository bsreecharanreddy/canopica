-- Runs once, on first container init (mounted into
-- /docker-entrypoint-initdb.d/) -- creates both databases and the
-- application role with the least privilege the app actually needs.
-- Operational schema migration is Flyway's job (run by portal-api on
-- startup, Task 12); this script only creates the databases to migrate
-- into.
create role ies_app with login password 'ies_app';
create database ies_operational owner ies_app;
create database ies_serving owner ies_app;
