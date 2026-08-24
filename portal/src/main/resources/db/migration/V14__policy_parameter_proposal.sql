-- A rule-authoring copilot's draft, awaiting a human decision (design doc
-- §2.3). Never a published figure: publishing an accepted proposal inserts
-- a brand-new policy_parameter_set, and this row only records that it
-- happened, in published_parameter_set_id.
create table policy_parameter_proposal (
    id                          uuid        primary key default gen_random_uuid(),
    current_parameter_set_id    uuid        not null references policy_parameter_set (id),
    source_excerpt              text        not null,
    proposed_values             jsonb       not null,
    status                      text        not null check (status in ('PENDING', 'ACCEPTED', 'REJECTED')),
    -- Who asked for the draft, and who decided on it. Both are recorded
    -- because "an AI proposed this" is never a complete answer to who
    -- changed a benefit figure -- a person asked, and a person accepted.
    proposed_by                 text        not null,
    reviewed_by                 text,
    reviewed_at                 timestamptz,
    published_parameter_set_id  uuid        references policy_parameter_set (id),
    -- Same provenance bar V13's ai.policy_qa_answer holds for an answer,
    -- applied to a draft that can end up deciding a benefit amount: which
    -- model, under which prompt version, from which excerpt.
    generation_model            text        not null,
    prompt_version              text        not null,
    created_at                  timestamptz not null default now(),
    -- A decision is a decision: it names a reviewer and a time, or it has
    -- not happened. Enforced rather than assumed, since the reviewer's
    -- identity is the whole accountability story for this table.
    constraint policy_parameter_proposal_reviewed_together check (
        (status = 'PENDING' and reviewed_by is null and reviewed_at is null)
        or (status in ('ACCEPTED', 'REJECTED') and reviewed_by is not null and reviewed_at is not null)
    ),
    -- Only an accepted proposal can point at a published set.
    constraint policy_parameter_proposal_published_only_when_accepted check (
        published_parameter_set_id is null or status = 'ACCEPTED'
    )
);

-- Deliberately mutable: status/reviewed_by/reviewed_at/published_parameter_set_id
-- update in place as a human reviews. This is a review-workflow record, not a
-- determination or a parameter value -- V3's immutability trigger does not apply
-- here and must not be copied onto this table. What V3 protects is the published
-- figure itself, and that protection is untouched: accepting a proposal *inserts*
-- a new parameter set rather than editing one.

-- Supports the reviewer's own screen: "what is waiting on me", newest first.
create index policy_parameter_proposal_pending_idx
    on policy_parameter_proposal (status, created_at desc);
