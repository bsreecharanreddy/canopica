-- Publishing a policy parameter set is the highest-stakes write in this
-- system: every determination made afterwards resolves its dollar figures
-- from it. policy_parameter_proposal already records who proposed and who
-- accepted, but that table is mutable by design (it is a review-workflow
-- record), so it cannot be the tamper-evident answer to "who published
-- this". The hash-chained audit log can, and this is exactly what roadmap
-- §3.6 built it for.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED'));
