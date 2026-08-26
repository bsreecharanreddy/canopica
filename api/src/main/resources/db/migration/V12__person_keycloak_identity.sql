-- Maps a citizen-authenticated identity to the person row they submitted as
-- head of household, the read-side counterpart to V7's worker mapping.
--
-- Not unique, unlike worker.keycloak_subject: IntakeService creates a fresh
-- person row on every submission (no "find and reuse an existing person"
-- lookup), so the same real citizen applying more than once over time -- a
-- second household, a later reapplication -- legitimately produces more
-- than one person row carrying their subject. A unique constraint would
-- reject that second submission outright; the ownership check (Task 2)
-- is written to accept a set of person ids for one subject, not exactly one.
alter table person add column keycloak_subject text;
create index idx_person_keycloak_subject on person (keycloak_subject);
