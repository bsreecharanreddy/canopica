{{ config(materialized='table') }}

-- No household_key here: program_request only carries application_id in
-- the operational schema, and 'application' is deliberately outside this
-- task's narrow bronze source list (see sources.yml's header comment).
-- Widening to carry household_key is Phase 1b's job, alongside the rest of
-- roadmap §3.4.2's tables.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'program_request') }}
)
select
    id               as program_request_key,
    application_id   as application_key,
    program_code,
    status,
    requested_on,
    is_expedited,
    _ingested_at     as loaded_at
from latest
where rn = 1
