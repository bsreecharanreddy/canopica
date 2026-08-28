-- An AI-drafted eligibility notice, awaiting worker/admin review (Phase 3
-- design doc §2.4/§2.6). Deliberately one table with a status lifecycle,
-- not a separate advisory table plus a published one the way ai.
-- policy_qa_answer sits apart from eligibility_determination -- a Policy
-- Q&A answer only ever *explains* a determination, but a notice's own
-- filled content *is* the eventual artifact once approved (design doc's
-- own reasoning). Closer in shape to policy_parameter_proposal (V14) --
-- a mutable row a human reviews and either advances or not.
create table notice (
    id                  uuid        primary key default gen_random_uuid(),
    program_request_id  uuid        not null references program_request (id),
    determination_id    uuid        not null references eligibility_determination (id),
    notice_type         text        not null check (notice_type in
                                ('APPROVAL', 'DENIAL', 'PENDING_VERIFICATION')),
    status              text        not null check (status in
                                ('DRAFT', 'APPROVED', 'REJECTED', 'SENT')),
    -- The fully filled template text -- every dollar amount/date already
    -- substituted programmatically (design doc §2.4), never edited by the
    -- LLM after the fact.
    content             text        not null,
    template_version    text        not null,
    language            text        not null default 'en',
    -- The deterministic pre-check's own output (design doc §2.4's
    -- validation gate), kept even after a human reviews -- a worker
    -- approving a notice whose own check failed is a real, auditable
    -- fact, not something to discard once reviewed.
    validation_result   jsonb       not null,
    -- Same provenance bar V13's ai.policy_qa_answer and V14's
    -- policy_parameter_proposal hold for anything AI-drafted that can end
    -- up in front of a household.
    generation_model    text        not null,
    prompt_version      text        not null,
    approved_by         text,
    approved_at         timestamptz,
    sent_at             timestamptz,
    created_at          timestamptz not null default now(),
    -- A decision is a decision: it names an approver and a time, or it
    -- has not happened yet. Same shape V14's own reviewed_together check
    -- enforces for policy_parameter_proposal.
    constraint notice_approved_together check (
        (status in ('DRAFT', 'REJECTED') and approved_by is null and approved_at is null)
        or (status in ('APPROVED', 'SENT') and approved_by is not null and approved_at is not null)
    ),
    -- Only an approved (or already-sent) notice can carry a sent_at.
    constraint notice_sent_only_when_approved check (
        sent_at is null or status = 'SENT'
    )
);

-- Deliberately mutable, same reasoning V14's own comment gives: this is a
-- review-workflow record, not a determination or a parameter value.
-- V5's append-only trigger does not apply here and must not be copied
-- onto this table.

-- Supports Task 6's reviewer screen: "what is waiting on me", oldest first
-- so a draft doesn't sit unseen behind a stream of newer ones.
create index notice_review_queue_idx on notice (status, created_at);

-- Widens the constraint for this task's own new event type only, same
-- "widen once per real need" pattern V16/V18/V19 already set --
-- NOTICE_APPROVED/NOTICE_SENT are Task 6's own real need, not this one's.
-- Written by the Python worker (correspondence_consumer.py), never by
-- Java's AuditService -- added to AuditEventType.java anyway, for the
-- same reason V19's own comment gives for DOCUMENT_CLASSIFIED:
-- JdbcAuditService#findBySubject would otherwise throw the first time the
-- case audit-trail endpoint read one back.
alter table audit_event drop constraint audit_event_event_type_check;

alter table audit_event add constraint audit_event_event_type_check
    check (event_type in
        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
         'CASE_VIEWED', 'VERIFICATION_UPDATED',
         'POLICY_PARAMETER_PUBLISHED', 'DOCUMENT_UPLOADED', 'DOCUMENT_CLASSIFIED',
         'NOTICE_DRAFTED'));
