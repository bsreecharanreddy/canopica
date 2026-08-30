{{ config(materialized='table') }}

-- Phase 4 Task 8: feeds the notice-rejection-rate metric. Grain is
-- (notice_month, notice_type, status), pre-aggregated like
-- mart_determination_outcomes -- no notice content, validation_result,
-- generation_model, or approver identity here, since a rejection-rate
-- ratio needs none of it and gold carries no PII.
select
    date_trunc('month', n.created_at)::date as notice_month,
    n.notice_type,
    n.status,
    count(*)                                as notice_count
from {{ ref('fct_notice') }} n
group by 1, 2, 3
