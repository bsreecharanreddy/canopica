-- Widens the constraint for this task's own new event type only, same
-- "widen once per real need" pattern V16/V18/V20/V21/V24 already set --
-- QC_DISCREPANCY_FLAGGED (Task 4) and QC_REVIEW_COMPLETED (Task 5) are
-- each their own task's real need, not this one's.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED', 'DOCUMENT_UPLOADED', 'DOCUMENT_CLASSIFIED',
         'NOTICE_DRAFTED', 'NOTICE_APPROVED', 'NOTICE_SENT', 'FRAUD_FLAG_RAISED',
         'FRAUD_FLAG_REVIEWED'));
