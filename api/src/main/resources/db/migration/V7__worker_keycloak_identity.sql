-- worker/case_assignment tables and worker.role's WORKER/SUPERVISOR/ADMIN
-- values already exist (V1, Phase 1a) -- reserved for this phase, never
-- wired up. This migration adds the one thing that was missing: a way to
-- map a real Keycloak-authenticated identity to a worker row.
alter table worker add column keycloak_subject text unique;
