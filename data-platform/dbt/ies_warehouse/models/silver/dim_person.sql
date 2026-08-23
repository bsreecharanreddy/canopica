{{ config(materialized='table') }}

-- Classify and tokenize here, not later: raw names and full dates of birth
-- stop at silver and never reach gold. ssn_token is already tokenized by
-- the operational system (see person.ssn_token's comment in
-- V1__core_entities.sql) -- there is no raw SSN anywhere in this system.
-- name_token comes from ies_data.governance.tokenize's vault-backed
-- get_or_create_token, landed as bronze.person_pii_tokens before this
-- model builds (Phase 1b Task 7). Reversible under a separate, audited
-- detokenize() call, unlike the one-way hash this replaced -- see
-- docs/design/2026-08-22-phase-1b-hardening-design.md's Task 7 correction
-- note for why that distinction is the actual gap being closed here.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'person') }}
),
tokens as (
    select *, row_number() over (partition by person_id order by _ingested_at desc) as rn
    from {{ source('bronze', 'person_pii_tokens') }}
)
select
    l.id                                     as person_key,
    l.ssn_token,
    extract(year from l.date_of_birth)::int   as birth_year,
    l.sex,
    l.is_us_citizen,
    t.name_token,
    l._ingested_at                            as loaded_at
from latest l
left join tokens t on t.person_id = l.id and t.rn = 1
where l.rn = 1
