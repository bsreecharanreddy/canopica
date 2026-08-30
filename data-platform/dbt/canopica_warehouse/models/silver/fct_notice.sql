{{ config(materialized='table') }}

-- Phase 4 Task 8: mart_notice_outcomes's own notice-rejection-rate source
-- -- one row per notice, deduplicated to the latest bronze landing (a
-- mutable row -- DRAFT -> APPROVED/REJECTED -> SENT, same posture
-- fct_payment_error_review already takes). Deliberately narrow: content,
-- validation_result, generation_model, prompt_version, and approver
-- identity aren't needed by any current gold consumer, so they stay out
-- of silver rather than carried "just in case".
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'notice') }}
)
select
    id                    as notice_key,
    program_request_id    as program_request_key,
    notice_type,
    status,
    created_at,
    _ingested_at          as loaded_at
from latest
where rn = 1
