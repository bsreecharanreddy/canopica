-- Fraud Risk Triage's scored output (Phase 4 design doc §2.2/§2.8): one
-- row per scored determination. Deliberately mutable -- review_outcome/
-- reviewed_by/reviewed_at update in place once a supervisor acts (Task 3)
-- -- a review decision about a flag, not a binding fact about the case
-- itself, same posture V14's policy_parameter_proposal and V20's notice
-- already take for a human-reviewed row. V5's append-only trigger does
-- not apply here.
create table fraud_risk_score (
    id                         uuid        primary key default gen_random_uuid(),
    program_request_id        uuid        not null references program_request (id),
    determination_id          uuid        not null references eligibility_determination (id),
    -- Min-max normalized against the fitted population at scoring time
    -- (score.py), not IsolationForest's own raw, unbounded score_samples
    -- output -- 0 = least anomalous case in that population, 1 = most.
    score                      numeric     not null check (score >= 0 and score <= 1),
    top_contributing_features  jsonb       not null,
    model_version              text        not null,
    scored_at                  timestamptz not null default now(),
    reviewed_by                text,
    reviewed_at                timestamptz,
    review_outcome             text        check (review_outcome in ('CONFIRMED_RISK', 'CLEARED')),
    -- Same shape V14's own reviewed_together check enforces for
    -- policy_parameter_proposal: a review decision names a reviewer and a
    -- time, or it has not happened yet.
    constraint fraud_risk_score_reviewed_together check (
        (review_outcome is null and reviewed_by is null and reviewed_at is null)
        or (review_outcome is not null and reviewed_by is not null and reviewed_at is not null)
    )
);

-- Task 3's review queue: unreviewed cases, highest risk first.
create index fraud_risk_score_review_queue_idx on fraud_risk_score (review_outcome, score desc);
