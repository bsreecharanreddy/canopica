{{ config(materialized='table') }}

-- parameter_set_key is a foreign key to dim_policy_parameter_set's SCD-2
-- rows -- this is what lets a report say "under the rules in force at the
-- time" instead of silently re-scoring history against whatever is current
-- today (roadmap §3.4.1).
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'eligibility_determination') }}
)
select
    id                          as determination_key,
    program_request_id          as program_request_key,
    policy_parameter_set_id     as parameter_set_key,
    benefit_month,
    as_of_date,
    eligible,
    benefit_amount,
    reason_code,
    policy_parameter_version,
    decided_at,
    _ingested_at                as loaded_at
from latest
where rn = 1
