{{ config(materialized='table') }}

-- The household_key fct_program_request's own comment flagged as missing
-- until 'application' widened bronze -- Phase 1b Task 5 is that widening.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'application') }}
)
select
    id             as application_key,
    household_id   as household_key,
    submitted_at,
    channel,
    _ingested_at   as loaded_at
from latest
where rn = 1
