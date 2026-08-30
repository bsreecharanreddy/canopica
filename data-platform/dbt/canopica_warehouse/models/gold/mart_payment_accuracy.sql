{{ config(materialized='table') }}

-- Real payment-error-rate reporting (Phase 4 Task 4): reviewed/
-- payment_error_amount now come from a left join to fct_payment_error_review,
-- QcSamplingService's own sampled re-derivation via DeterminationService.
-- reproduce() -- replacing the earlier placeholder's hardcoded false/null.
-- A determination never sampled still shows reviewed = false/null, exactly
-- matching that placeholder default; a sampled determination shows whether
-- QC actually found a discrepancy. Grain is still one row per eligible
-- determination (a denial produces no payment, so there is nothing to
-- review for accuracy).
select
    d.determination_key,
    d.benefit_month,
    r.program_code,
    d.benefit_amount                    as paid_amount,
    per.determination_key is not null   as reviewed,
    per.error_amount                    as payment_error_amount
from {{ ref('fct_eligibility_determination') }} d
join {{ ref('fct_program_request') }} r on r.program_request_key = d.program_request_key
left join {{ ref('fct_payment_error_review') }} per on per.determination_key = d.determination_key
where d.eligible
