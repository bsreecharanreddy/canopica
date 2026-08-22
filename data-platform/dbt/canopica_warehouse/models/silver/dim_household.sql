{{ config(materialized='table') }}

-- Same "classify here, not later" rule as dim_person: street address and
-- city are dropped rather than carried into the warehouse at all -- county
-- is what Phase 1b's row-level authorization and reporting actually need,
-- and a full street address is materially more identifying than what any
-- planned mart uses.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'household') }}
)
select
    id               as household_key,
    head_person_id   as head_person_key,
    county,
    state,
    zip_code,
    _ingested_at     as loaded_at
from latest
where rn = 1
