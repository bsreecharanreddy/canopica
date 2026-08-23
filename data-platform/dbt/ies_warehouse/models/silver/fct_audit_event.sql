{{ config(materialized='table') }}

-- audit_event rows are append-only and never updated (the V6 hash-chain
-- trigger enforces it) -- the latest-_ingested_at dedup here exists only to
-- collapse duplicate landings across ingestion batches, the same reason
-- every other silver model does it, not because any one row's content ever
-- changes. payload is kept as raw jsonb: its shape varies by event_type
-- (CASE_VIEWED's `in_assignment` flag, VERIFICATION_UPDATED's request/
-- response), so it stays silver-only and unflattened -- gold marts that need
-- one field out of it (mart_access_review's `in_assignment`) extract it
-- there, not here. prev_hash/hash are deliberately not carried forward:
-- chain verification is the operational database's job (verify_chain(),
-- Task 6), not something this reporting copy re-derives.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'audit_event') }}
)
select
    id             as audit_event_key,
    occurred_at,
    event_type,
    actor_id,
    subject_type,
    subject_id,
    payload,
    _ingested_at   as loaded_at
from latest
where rn = 1
