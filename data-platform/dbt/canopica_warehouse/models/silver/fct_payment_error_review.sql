{{ config(materialized='table') }}

-- Phase 4 Task 4: mart_payment_accuracy's own reviewed/payment_error_amount
-- columns need this -- one row per sampled determination, deduplicated to
-- the latest bronze landing (a mutable row -- Task 5's own review fields
-- update in place, same posture fct_fraud_risk_score already takes).
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'payment_error_review') }}
)
select
    id                    as payment_error_review_key,
    determination_id      as determination_key,
    original_amount,
    reproduced_amount,
    error_amount,
    review_outcome,
    sampled_at,
    _ingested_at          as loaded_at
from latest
where rn = 1
