{{ config(materialized='table') }}

-- Classify and tokenize here, not later: raw names and full dates of birth
-- stop at silver and never reach gold. ssn_token is already tokenized by
-- the operational system (see person.ssn_token's comment in
-- V1__core_entities.sql) -- there is no raw SSN anywhere in this system.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'person') }}
)
select
    id                                             as person_key,
    ssn_token,
    extract(year from date_of_birth)::int          as birth_year,
    sex,
    is_us_citizen,
    sha256(lower(first_name || '|' || last_name))  as name_hash,
    _ingested_at                                   as loaded_at
from latest
where rn = 1
