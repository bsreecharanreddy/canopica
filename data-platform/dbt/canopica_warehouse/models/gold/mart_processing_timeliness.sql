{{ config(materialized='table') }}

-- Now that Task 6 makes program_request.is_expedited real (7 CFR
-- 273.2(i)), this mart -- deferred from Task 5 for exactly this reason --
-- can finally compute something meaningful: SNAP's real processing-time
-- standards (30 days normal, 7 days expedited, roadmap §3.4.2) instead of
-- the always-false column Task 5 would have had to build against.
-- Phase 4 Task 8: program_code added for "time-to-resolution by case
-- type" -- the join to fct_program_request already existed for
-- is_expedited, so this is a free column, not a new join.
select
    d.determination_key,
    d.program_request_key,
    r.program_code,
    r.is_expedited,
    a.submitted_at,
    d.decided_at,
    (d.decided_at::date - a.submitted_at::date)                       as processing_days,
    case when r.is_expedited then 7 else 30 end                       as standard_days,
    (d.decided_at::date - a.submitted_at::date)
        > (case when r.is_expedited then 7 else 30 end)               as missed_standard
from {{ ref('fct_eligibility_determination') }} d
join {{ ref('fct_program_request') }} r on r.program_request_key = d.program_request_key
join {{ ref('fct_application') }} a on a.application_key = r.application_key
