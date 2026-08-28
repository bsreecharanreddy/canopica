-- Task 6 (notice review, approval & dispatch): the two audit event types
-- V20's own comment already reserved this task's real need for.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED', 'DOCUMENT_UPLOADED', 'DOCUMENT_CLASSIFIED',
         'NOTICE_DRAFTED', 'NOTICE_APPROVED', 'NOTICE_SENT'));

-- A real gap V20 left open: notice_approved_together already requires
-- approved_by/approved_at together for APPROVED/SENT, but nothing
-- symmetric exists for REJECTED -- a worker rejecting an AI-drafted
-- notice would otherwise leave zero reviewer attribution anywhere, not
-- even a plain column, which does not meet this project's own
-- explainability bar. Mirrors policy_parameter_proposal's (V14)
-- reviewed_by/reviewed_at symmetry between its own accept/reject paths,
-- rather than a new mechanism.
alter table notice add column rejected_by text;
alter table notice add column rejected_at timestamptz;

alter table notice add constraint notice_rejected_together check (
    (status <> 'REJECTED' and rejected_by is null and rejected_at is null)
    or (status = 'REJECTED' and rejected_by is not null and rejected_at is not null)
);
