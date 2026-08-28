-- Phase 3 design doc §2.6: a system-of-record pointer into MinIO, not the
-- document content itself -- same tier as verification/benefit_month, not
-- ai.policy_qa_answer's shape. object_key is derived from program_request_id
-- and this row's own generated id, never from the uploaded filename (§2.1's
-- stated reason: an applicant-controlled filename must not be able to
-- traverse or collide with another case's object).
create table document (
    id                      uuid primary key,
    program_request_id      uuid        not null references program_request (id),
    object_key              text        not null unique,
    content_type            text        not null,
    uploaded_by             text        not null,
    uploaded_at             timestamptz not null default now(),
    classification_status   text        not null default 'PENDING'
                                 check (classification_status in
                                     ('PENDING', 'CLASSIFIED', 'CONFIRMED', 'REJECTED'))
);
create index document_program_request_idx on document (program_request_id);
