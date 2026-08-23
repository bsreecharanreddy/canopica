{{ config(materialized='table') }}

-- One row per CASE_VIEWED audit event -- who looked at which case, and
-- whether it was their own assignment (design doc §3.4.2). in_assignment
-- is Task 2's payload field (WorkerCaseController's checkCaseloadAccess
-- result); a false here is exactly what a real access-review process is
-- meant to triage first, since flag-and-log (not sealing) means every role
-- that could already see a case still can.
select
    a.audit_event_key,
    a.occurred_at,
    w.worker_key,
    w.worker_name,
    w.role                                     as worker_role,
    a.subject_id                               as program_request_key,
    (a.payload ->> 'in_assignment')::boolean   as in_assignment
from {{ ref('fct_audit_event') }} a
left join {{ ref('dim_worker') }} w on w.keycloak_subject = a.actor_id
where a.event_type = 'CASE_VIEWED'
