{{ config(materialized='table') }}

with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'verification') }}
)
select
    id                    as verification_key,
    program_request_id    as program_request_key,
    data_element,
    status,
    due_on,
    satisfied_on,
    _ingested_at          as loaded_at
from latest
where rn = 1
