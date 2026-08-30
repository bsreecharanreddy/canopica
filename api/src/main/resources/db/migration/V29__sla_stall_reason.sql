-- Case SLA/Compliance Monitor's pre-generated stall-reason cache (Phase 4
-- Task 6, design doc §2.4). Refreshed on its own intra-day cadence by the
-- Airflow-triggered ai/sla_monitor batch job (ai/sla_monitor/service.py
-- writes here directly -- there is no triggering Java write to couple a
-- transactional-outbox enqueue to, just a scheduled refresh, so unlike
-- fraud_scoring/qc_summary this has no pgmq queue in front of it);
-- AtRiskCaseQuery reads this table directly on every request, keeping
-- GET /api/sla/at-risk-queue a plain, fast SQL query with no LLM call on
-- the live request path. Operational, not a mart -- design doc §2.4's own
-- reasoning is that same-day currency is the entire point, which a
-- nightly dbt build structurally can't give -- so this table is
-- deliberately never bronze/silver/gold ingested.
create table sla_stall_reason (
    program_request_id uuid        primary key references program_request (id),
    reason              text        not null,
    generated_at        timestamptz not null default now()
);
