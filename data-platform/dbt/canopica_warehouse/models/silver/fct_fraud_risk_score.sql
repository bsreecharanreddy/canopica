{{ config(materialized='table') }}

-- Phase 4 Task 3: mart_fairness_audit's own fraud_triage axis needs the
-- real scored population. Same "latest by _ingested_at wins" dedup
-- fct_eligibility_determination already uses -- fraud_risk_score is a
-- mutable row (Task 3's own review fields update in place), so a later
-- ingestion batch can carry a newer review_outcome for the same id.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'fraud_risk_score') }}
)
select
    id                  as fraud_risk_score_key,
    determination_id    as determination_key,
    program_request_id  as program_request_key,
    score,
    model_version,
    scored_at,
    review_outcome,
    _ingested_at         as loaded_at
from latest
where rn = 1
