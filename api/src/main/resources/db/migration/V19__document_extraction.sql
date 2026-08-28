-- Phase 3 Task 3: where the worker persists a document's classification
-- result (design doc §2.3) so Task 4's review UI can read it. One jsonb
-- column carrying the whole `DocumentExtraction` (document_type, fields,
-- matched_verification_ids, generation_model, prompt_version) -- the same
-- "schema-validated result on the row itself" shape `policy_qa_answer`
-- and (per the Task 5 plan) `notice.validation_result` already use --
-- plus one plain numeric column for the *minimum* per-field confidence,
-- kept out of the jsonb blob because Task 4's review-queue endpoint has
-- to `order by` it, and ordering by a jsonb path is the kind of thing
-- this codebase's own tables avoid when a real column will do
-- (verification.status, not a jsonb status field, is the precedent).
alter table document add column extraction jsonb;
alter table document add column extraction_confidence numeric(4, 3)
    check (extraction_confidence between 0 and 1);

-- Widens the constraint for this task's own new event type only, same
-- "widen once per real need" pattern V16/V18 already set. Written by the
-- Python worker (document_intake_consumer.py), never by Java's
-- AuditService -- added to AuditEventType.java anyway, because
-- JdbcAuditService#findBySubject deserializes event_type back into that
-- enum on every read, and the case audit-trail endpoint (WorkerCaseController)
-- would throw IllegalArgumentException the first time it read one back
-- if the Java side didn't know this value existed.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED', 'DOCUMENT_UPLOADED', 'DOCUMENT_CLASSIFIED'));
