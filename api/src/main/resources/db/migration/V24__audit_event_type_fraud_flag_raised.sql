-- Widens the constraint for this task's own new event type only, same
-- "widen once per real need" pattern V16/V18/V20/V21 already set --
-- FRAUD_FLAG_REVIEWED (Task 3), QC_DISCREPANCY_FLAGGED (Task 4), and
-- QC_REVIEW_COMPLETED (Task 5) are each their own task's real need, not
-- this one's. Deviates from the Phase 4 implementation plan's Task 2 file
-- list, which called for widening all four of this phase's event types at
-- once as a single V25 migration -- corrected here for the same reason
-- V18's own comment already corrected an identical pre-widening mistake
-- the Phase 3 plan made: this project's real migration history applies
-- strictly in landing order, and reserving V24 here for Task 4's
-- payment_error_review while this constraint change lands as V25 would
-- break Flyway's validation (outOfOrder is not enabled --
-- application.yml has no such setting) the moment Task 4's actual V24
-- file is added after this one has already applied. Renumbered
-- V23 (fraud_risk_score) / V24 (this file) instead; V25 is Task 4's real
-- next number when it lands, not reserved in advance.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED', 'DOCUMENT_UPLOADED', 'DOCUMENT_CLASSIFIED',
         'NOTICE_DRAFTED', 'NOTICE_APPROVED', 'NOTICE_SENT', 'FRAUD_FLAG_RAISED'));
