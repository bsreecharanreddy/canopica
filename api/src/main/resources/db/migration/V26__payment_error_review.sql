-- QC / Payment Error Rate Assistant's sampled re-derivation (Phase 4
-- design doc §2.3): one row per sampled determination. Deliberately
-- mutable -- review_outcome/reviewed_by/reviewed_at update in place once
-- a supervisor acts (Task 5), same posture V23's fraud_risk_score already
-- takes for a human-reviewed row.
create table payment_error_review (
    id                    uuid        primary key default gen_random_uuid(),
    determination_id      uuid        not null references eligibility_determination (id),
    original_amount       numeric     not null,
    -- QcSamplingService.reproduce()'s own fresh benefit_amount, re-derived
    -- from the SAME stored facts/parameter-set id the original decision
    -- used (roadmap §3.5's reproducibility guarantee) -- a diff here means
    -- the DMN model itself produced a different answer since the original
    -- decision, not a parameter-set change.
    reproduced_amount     numeric     not null,
    error_amount          numeric     not null,
    -- SnapDecision.trace() from the reproduction call, captured here
    -- because reproduce() itself never persists anything (it's read-only
    -- -- JdbcDeterminationService's own doc comment) -- ai/qc_assistant's
    -- summarize.py grounds its discrepancy explanation in this alongside
    -- the original's own determination_trace.decision_results, per
    -- constraint 21.
    reproduced_trace      jsonb       not null,
    ai_summary            text,
    sampled_at            timestamptz not null default now(),
    reviewed_by           text,
    reviewed_at           timestamptz,
    review_outcome        text        check (review_outcome in ('CONFIRMED_ERROR', 'DISMISSED')),
    -- Same shape V23's own fraud_risk_score_reviewed_together check
    -- enforces: a review decision names a reviewer and a time, or it has
    -- not happened yet.
    constraint payment_error_review_reviewed_together check (
        (review_outcome is null and reviewed_by is null and reviewed_at is null)
        or (review_outcome is not null and reviewed_by is not null and reviewed_at is not null)
    ),
    -- QcSamplingService excludes already-sampled determinations from its
    -- own selection query, but that check alone isn't race-safe against
    -- two overlapping sample runs -- this is the real guarantee.
    constraint payment_error_review_determination_unique unique (determination_id)
);

-- Task 5's review queue: unreviewed discrepancies, largest error first.
-- Partial -- a zero-diff sampled case is real evidence for the mart
-- (a clean re-derivation), but never needs a reviewer's attention.
create index payment_error_review_review_queue_idx
    on payment_error_review (review_outcome, error_amount desc)
    where error_amount <> 0;
