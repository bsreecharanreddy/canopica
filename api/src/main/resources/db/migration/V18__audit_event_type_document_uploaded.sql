-- Widens the constraint for this task's own new event type only, same
-- "widen once per real need" pattern V16 already set for
-- POLICY_PARAMETER_PUBLISHED -- not pre-widened for Task 5's NOTICE_*
-- types too (the Phase 3 implementation plan's own Task 2 file list
-- claimed that, incorrectly; corrected here rather than carried into the
-- migration itself). Task 3's DOCUMENT_CLASSIFIED and Task 5's NOTICE_*
-- types each get their own migration when that task actually lands.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED', 'DOCUMENT_UPLOADED'));
