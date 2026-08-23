{{ config(materialized='table') }}

-- case_assignment has no dedicated silver fact of its own (design doc
-- §3.4.2's six new Task 5 models are dim_worker/dim_program/fct_application/
-- fct_verification/fct_benefit_month/fct_audit_event -- case_assignment
-- isn't one of them). Deduped straight from bronze here instead, the same
-- latest-per-natural-key pattern every silver model uses, since this mart
-- is currently its only consumer. "Active" means still-open (effective_to
-- is null) -- CaseAssignmentService.reassign() end-dates the prior row the
-- moment a new one starts, so there is never more than one active row per
-- household.
with latest_assignment as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'case_assignment') }}
),
active_assignment as (
    select worker_id, household_id
    from latest_assignment
    where rn = 1 and effective_to is null
)
select
    w.worker_key,
    w.worker_name,
    w.role,
    count(a.household_id)  as active_case_count
from {{ ref('dim_worker') }} w
left join active_assignment a on a.worker_id = w.worker_key
group by 1, 2, 3
