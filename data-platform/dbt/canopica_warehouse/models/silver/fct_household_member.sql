{{ config(materialized='table') }}

-- Bridges household_key <-> person_key -- bronze has carried household_member since Phase 1b
-- Task 5 widened medallion coverage, but no silver model was ever built on top of it until
-- Phase 4's fairness audit (Task 1) needed one to resolve "which person's demographics does this
-- determination's household map to."
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'household_member') }}
)
select
    id                as household_member_key,
    household_id      as household_key,
    person_id         as person_key,
    relationship,
    effective_from,
    effective_to,
    _ingested_at      as loaded_at
from latest
where rn = 1
