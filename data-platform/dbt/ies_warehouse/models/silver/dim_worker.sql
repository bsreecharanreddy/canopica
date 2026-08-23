{{ config(materialized='table') }}

-- Unlike dim_person, worker_name/email carry through as real text rather
-- than a hash: the whole point of mart_access_review and mart_worker_
-- caseload is naming which staff member did what, and workers are IES
-- staff, not the applicant population is_pii_column's gate protects.
-- keycloak_subject is kept here (it's how fct_audit_event.actor_id joins
-- back to a worker) but never flows into a gold model.
with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'worker') }}
)
select
    id                as worker_key,
    full_name         as worker_name,
    email,
    role,
    keycloak_subject,
    _ingested_at      as loaded_at
from latest
where rn = 1
