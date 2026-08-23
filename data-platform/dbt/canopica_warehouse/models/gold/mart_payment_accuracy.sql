{{ config(materialized='table') }}

-- Placeholder shape, not the QC computation: real payment-error-rate logic
-- needs Phase 4's QC / Payment Error Rate Assistant (roadmap §5), which
-- re-derives what a determination *should* have produced and diffs it
-- against what was actually paid. Neither exists yet. This mart exists and
-- is tested now so the columns Phase 4 needs to fill in are already
-- contracted for downstream reporting -- every row's `reviewed` is false
-- and `payment_error_amount` is null until that phase lands. Grain is one
-- row per eligible determination (a denial produces no payment, so there is
-- nothing to review for accuracy).
select
    d.determination_key,
    d.benefit_month,
    r.program_code,
    d.benefit_amount        as paid_amount,
    false                   as reviewed,
    cast(null as numeric)   as payment_error_amount
from {{ ref('fct_eligibility_determination') }} d
join {{ ref('fct_program_request') }} r on r.program_request_key = d.program_request_key
where d.eligible
