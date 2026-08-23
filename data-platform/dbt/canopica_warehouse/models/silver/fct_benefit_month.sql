{{ config(materialized='table') }}

with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'benefit_month') }}
)
select
    id                    as benefit_month_key,
    program_request_id    as program_request_key,
    benefit_month,
    _ingested_at          as loaded_at
from latest
where rn = 1
