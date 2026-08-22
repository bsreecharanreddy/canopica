# Phase 1b — Hardening: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> Execute tasks in order, one commit per completed task, `docs/STATUS.md`
> updated in that same commit (CLAUDE.md, "Conventions"). Run the
> `ies-task-checkpoint` skill's gate (`make test`, `make lint`, STATUS.md,
> one commit, push) after every task.

**Goal:** Make the Phase 1a walking skeleton production-shaped: real
identity, real row-level authorization, a real (mocked) external
interface, real orchestration, a fuller warehouse, real governance,
accessibility, and observability.

**Spec:** `docs/design/2026-08-21-full-system-and-phased-roadmap.md` §5
(what), `docs/design/2026-08-22-phase-1b-hardening-design.md` (how — read
this one first, it resolves every open question this plan assumes as
settled), `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`
(fidelity/cost rationale for every substitution below).

**Starting point, worth internalizing before Task 1:** Phase 1a's Task 2
deliberately over-built the operational schema for this phase, then never
wired any of it up. `worker`, `case_assignment`, and `verification`
tables already exist; so do `program_request.is_expedited` and
`audit_event`'s `VERIFICATION_UPDATED` type. Every task below says
explicitly what's already there vs. genuinely new — check `docs/design/
2026-08-22-phase-1b-hardening-design.md`'s §2 for the reasoning if a
task's scope looks smaller than expected; it usually is, on purpose.

---

## Global constraints

Everything Phase 1a's plan stated still applies (never name a real
agency; AI drafts, deterministic systems decide — no LLM touches
anything in this phase either; full suite before every push; one commit
per task with `docs/STATUS.md` in the same commit; effective dating;
append-only determinations; synthetic data only; local-first, $0). Two
more, specific to this phase:

10. **Don't re-create schema that already exists.** Check
    `portal/src/main/resources/db/migration/` and
    `portal/src/main/java/ies/portal/domain/` before writing a migration
    or an entity — Phase 1a's Task 2 over-built on purpose (see above).
11. **Every substitution this phase makes gets a tradeoffs-doc row or
    tightened existing row**, per the `ies-design-decision` skill — most
    are already recorded in the design doc's §3; a task that finds a new
    one records it the same way.

### New dependencies this phase

| Component | Choice | Why |
|---|---|---|
| Identity | Keycloak 26.x (`quay.io/keycloak/keycloak`), two realms | Design doc §2.6 |
| Portal auth | `spring-boot-starter-oauth2-resource-server`, replacing `HardcodedRoleFilter` | Standard Spring Security JWT resource-server pattern |
| Web auth | `react-oidc-context` (thin wrapper over `oidc-client-ts`), Authorization Code + PKCE | Standard SPA OIDC pattern, no client secret in the browser |
| Orchestration | Apache Airflow 2.10.x, `LocalExecutor`, `apache/airflow` image | Design doc §2.5 |
| Tracing | Jaeger all-in-one (`jaegertracing/all-in-one`) | Design doc §2.5 |
| Metrics | Prometheus + Grafana (`prom/prometheus`, `grafana/grafana`) | Design doc §2.5 |
| Portal OTel | `spring-boot-starter-actuator` + Micrometer Tracing (`micrometer-tracing-bridge-otel`) + `opentelemetry-exporter-otlp` | Spring Boot's own OTel integration path |
| Data-platform OTel | `opentelemetry-sdk`, `opentelemetry-exporter-otlp` (Python) | Manual span instrumentation around pipeline stages |
| Accessibility | `eslint-plugin-jsx-a11y`, `vitest-axe` | Already-standard React a11y tooling |
| Reference cloud | Terraform (not applied), `azurerm` provider | Design doc, roadmap §3.7 |

### Prerequisites before Task 1

- [ ] Docker Desktop running (`docker info` succeeds) — Keycloak,
      Airflow, Jaeger, Prometheus, and Grafana all add new containers to
      `infra/docker-compose.yml`; this machine's resource headroom should
      be checked before bringing all of it up alongside the existing
      stack.
- [ ] The signed-in Simulator/browser session concern from lore-native
      doesn't apply here (web-only), but note: Task 1 changes how the
      portal authenticates entirely — expect to re-log-in to the portal
      UI after that task lands, same as any auth-layer change would.

---

## File structure (additions only)

```
integrated-eligibility-system/
  portal/src/main/resources/db/migration/
    V7__worker_keycloak_identity.sql       <- Task 1
    V8__household_sensitivity.sql          <- Task 2
    V9__verification_response.sql          <- Task 3
    V10__household_resources.sql           <- Task 6
    V11__pii_token_vault.sql               <- Task 7
  portal/src/main/java/ies/portal/
    config/SecurityConfig.java             <- modified, Task 1
    config/KeycloakWorkerSyncFilter.java   <- Task 1
    caseload/CaseAssignmentService.java    <- Task 2
    verification/MockVerificationService.java <- Task 3
    verification/VerificationController.java   <- Task 3
    observability/ (none — auto-instrumented via starters) <- Task 9
  portal/web/src/
    auth/oidc-config.ts                    <- Task 1, replaces role-header switch
    auth/RoleContext.tsx                   <- modified, now reads real claims
  identity/
    realm-export/ies-citizens-realm.json   <- Task 1
    realm-export/ies-workers-realm.json    <- Task 1
    README.md                              <- Task 1
  infra/
    docker-compose.yml                     <- modified: +keycloak, +airflow, +jaeger, +prometheus, +grafana
    airflow/dags/ies_pipeline_dag.py       <- Task 4
    airflow/Dockerfile                     <- Task 4 (if a custom image is needed)
    observability/prometheus.yml           <- Task 9
    observability/grafana-provisioning/    <- Task 9
    azure/                                 <- Task 10, reference only
      main.tf variables.tf outputs.tf providers.tf
      README.md
  dbt/ies_warehouse/models/silver/
    dim_worker.sql dim_program.sql fct_application.sql
    fct_verification.sql fct_benefit_month.sql fct_audit_event.sql   <- Task 5
  dbt/ies_warehouse/models/gold/
    mart_processing_timeliness.sql mart_payment_accuracy.sql
    mart_worker_caseload.sql mart_access_review.sql                  <- Task 5
  data-platform/src/ies_data/
    governance/tokenize.py                 <- Task 7
    observability/tracing.py               <- Task 9
  docs/design/compliance-mapping.md        <- Task 7
```

---

## Task list

| # | Task | Deliverable |
|---|---|---|
| 1 | Keycloak — citizen + worker realms | Real OIDC tokens replace `X-IES-Role`; e2e test uses a real token |
| 2 | Row-level authorization | `CASE_ASSIGNMENT` activated; unassigned `WORKER` gets 403; `SUPERVISOR` access logged |
| 3 | Mock external verification interface | `verification` activated; safeguarded response; audited |
| 4 | Airflow orchestration | DAG runs the real pipeline on a schedule, visible in Airflow's UI |
| 5 | Full medallion coverage | 6 new silver models, 4 new gold marts, dbt tests green |
| 6 | Reporting widened | Real `is_expedited`; `mart_processing_timeliness` against real 30/7-day standards |
| 7 | Governance completed | PII tokenized in silver; `compliance-mapping.md` written |
| 8 | Accessibility | axe-clean on the three main portal pages; a11y lint in CI |
| 9 | Observability | Traces in Jaeger, metrics in Grafana, for a real request/pipeline run |
| 10 | Reference Terraform for Azure | `terraform validate`/`fmt -check` clean; not applied |

---

## Task 1: Keycloak — citizen + worker realms

Replaces `HardcodedRoleFilter` (its own class comment already names this
task as its replacement). Two realms: `ies-citizens` (customer
self-service accounts) and `ies-workers` (`WORKER`/`SUPERVISOR`/`ADMIN`
realm roles — the schema for those three values already exists on
`worker.role`, see the design doc §2.1).

**Files:**
- Create: `identity/realm-export/ies-citizens-realm.json`,
  `ies-workers-realm.json` — declarative realm config, imported on
  Keycloak container start (`--import-realm`), reviewable in a diff same
  as the TMDL semantic model is (roadmap's own "model-as-code" preference
  applied here).
- Create: `portal/src/main/resources/db/migration/
V7__worker_keycloak_identity.sql`
- Modify: `portal/src/main/java/ies/portal/config/SecurityConfig.java`
- Create: `portal/src/main/java/ies/portal/config/
KeycloakWorkerSyncFilter.java`
- Delete: `portal/src/main/java/ies/portal/config/
HardcodedRoleFilter.java`
- Create: `portal/web/src/auth/oidc-config.ts`
- Modify: `portal/web/src/auth/RoleContext.tsx` (or wherever the header
  switch lives — reads real Keycloak realm roles instead)
- Modify: `infra/docker-compose.yml` (+`keycloak` service)
- Modify: `data-platform/tests/test_end_to_end.py`, `docs/demo.md`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Keycloak's `/realms/ies-workers/protocol/openid-connect/
token` endpoint (Direct Access Grants enabled on a `test-worker` client
  for `test_end_to_end.py`'s own token fetch — same "hit the real thing"
  standard as everything else in that test, not a stub).
- Produces: every previously-`X-IES-Role`-gated endpoint now expects
  `Authorization: Bearer <jwt>`; `Authentication#getName()` (used
  everywhere as `decided_by`/`actor_id`) becomes the JWT's `sub` claim
  instead of the literal role string.

```sql
-- V7__worker_keycloak_identity.sql
alter table worker add column keycloak_subject text unique;
```

- [ ] **Step 1: Realm exports.** `ies-workers` realm: client
      `ies-portal-api` (confidential, for resource-server validation),
      client `ies-portal-web` (public, PKCE), client `test-worker`
      (confidential, Direct Access Grants enabled, test-only — its
      secret lives in `.env.example` as a placeholder, real value never
      committed). Realm roles `WORKER`, `SUPERVISOR`, `ADMIN`. Two seeded
      test users matching `docs/demo.md`'s existing walkthrough.
      `ies-citizens` realm: simpler, one client, self-registration
      enabled (citizens create their own accounts — no admin
      provisioning, matching real intake).
- [ ] **Step 2: `V7` migration + `KeycloakWorkerSyncFilter`.** On a valid
      worker-realm JWT with no matching `worker.keycloak_subject`, this
      filter creates the `worker` row (name/email from JWT claims, role
      from the JWT's realm roles) before the request reaches a
      controller — first-login provisioning, not a separate admin step.
- [ ] **Step 3: `SecurityConfig` swap.**
      `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`, issuer URI
      pointing at the `ies-workers` realm for worker endpoints and
      `ies-citizens` for citizen endpoints (two resource-server chains,
      matched by path, same shape Spring Security supports natively for
      multi-issuer setups). Role check becomes
      `hasAuthority("SCOPE_...")`/`hasRole(...)` off the JWT's realm
      roles claim instead of the header.
- [ ] **Step 4: `AuthorizationTest` rewritten** against real tokens
      fetched from the running Keycloak (Testcontainers' Keycloak module,
      or the already-running Compose Keycloak if this test class
      switches to needing the full stack — decide at implementation time
      based on which keeps the test fast; either is a legitimate choice,
      state which was picked and why in the STATUS.md verification row).
      Assert: a citizen-realm token gets 403 from a worker endpoint; an
      expired/malformed token gets 401; a worker-realm token with no
      `worker` row yet gets provisioned on first use (not rejected).
- [ ] **Step 5: React OIDC.** `oidc-config.ts` wraps `react-oidc-context`
      pointed at the citizen or worker realm depending on which app
      entry the user lands on; `RoleContext` reads the decoded token's
      realm roles instead of a manually-flipped switch. The existing
      "Viewing as Customer/Worker" UI toggle from Phase 1a's demo becomes
      a real login screen per realm.
- [ ] **Step 6: Adapt `test_end_to_end.py` and `docs/demo.md`.** The e2e
      test's `_run_determination`/`_get_trace` helpers fetch a real
      bearer token from `ies-workers`' token endpoint using
      `test-worker`'s Direct Access Grant before calling the portal API,
      replacing the `X-IES-Role: WORKER` header entirely. Re-run the
      full demo.md walkthrough by hand (same standard as Phase 1a's
      Task 13) since the login step is now genuinely different — note
      what's observed, don't assume the old screenshots still apply.
- [ ] **Step 7: Full suite + commit.**

---

## Task 2: Row-level authorization

`case_assignment` and `worker.role`'s `SUPERVISOR` value already exist
(design doc §2.1) — this task activates them. Depends on Task 1 (needs a
real `worker.id` to assign to).

**Files:**
- Create: `portal/src/main/resources/db/migration/
V8__household_sensitivity.sql`
- Create: `portal/src/main/java/ies/portal/caseload/
CaseAssignmentService.java`
- Modify: `portal/src/main/java/ies/portal/domain/Household.java`
  (`isSensitive`, `sensitiveReason`)
- Modify: `portal/src/main/java/ies/portal/api/
WorkerCaseController.java` (authorization check + `CASE_VIEWED`
  payload)
- Create: `portal/src/main/java/ies/portal/api/
SupervisorController.java` (reassignment + sensitivity-flag endpoints)
- Create: `portal/src/test/java/ies/portal/caseload/
CaseAssignmentServiceTest.java`
- Modify: `portal/src/test/java/ies/portal/api/
WorkerCaseControllerTest.java`
- Modify: `docs/STATUS.md`

```sql
-- V8__household_sensitivity.sql
alter table household add column is_sensitive boolean not null default false;
alter table household add column sensitive_reason text;
```

**Interfaces:**
- `CaseAssignmentService.assignOnFirstTouch(householdId, workerId)` —
  called from `WorkerCaseController` before returning case detail; no-op
  if an active assignment already exists.
- New endpoints: `POST /api/supervisor/households/{id}/reassign
{workerId}` and `PUT /api/supervisor/households/{id}/sensitivity
{isSensitive, reason}`, both `SUPERVISOR`-only.

- [ ] **Step 1: `V8` migration + `Household` entity fields.**
- [ ] **Step 2: `CaseAssignmentService`, test-first.** Test: a household
      with no assignment gets one on first case-detail view, keyed to
      the viewing worker; a second different worker viewing the same
      household afterward does *not* get a new assignment (the first
      claim sticks); reassignment by a `SUPERVISOR` replaces the active
      assignment (`effective_to` set on the old row, a new row inserted
      — effective-dated, same convention as everything else in this
      schema).
- [ ] **Step 3: Authorization check in `WorkerCaseController`.** The join
      described in the design doc (§2.1):
      `program_request → application → household → case_assignment`.
      A `WORKER` whose id doesn't match the household's active
      assignment gets 403. A `SUPERVISOR` always gets 200. Test both.
- [ ] **Step 4: `CASE_VIEWED` payload gains `in_assignment`.** Change
      `WorkerCaseController`'s existing
      `auditService.append(AuditEventType.CASE_VIEWED, ..., Map.of())`
      call to compute and include `in_assignment: boolean` (true for the
      assigned worker or for any request that isn't a supervisor
      override). Test: querying `audit_event` after a supervisor views
      an unassigned household shows `in_assignment: false` in the
      payload.
- [ ] **Step 5: Sensitivity flag + endpoint.** `SUPERVISOR`-only `PUT`;
      test a `WORKER` gets 403 attempting it.
- [ ] **Step 6: Full suite + commit.**

---

## Task 3: Mock external verification interface

`verification` and `VERIFICATION_UPDATED` already exist, unused (design
doc §2.2). This task activates both rather than creating parallel schema.

**Files:**
- Create: `portal/src/main/resources/db/migration/
V9__verification_response.sql`
- Modify: `portal/src/main/java/ies/portal/intake/IntakeService.java`
  (creates a `verification` row per program request, `data_element =
'INCOME'`, `status = 'OUTSTANDING'`)
- Create: `portal/src/main/java/ies/portal/verification/
MockVerificationService.java`, `VerificationController.java`
- Create: `portal/src/main/java/ies/portal/domain/
VerificationResponse.java`, `repo/VerificationResponseRepository.java`
- Create: `portal/src/test/java/ies/portal/verification/
MockVerificationServiceTest.java`, `VerificationControllerTest.java`
- Modify: `docs/STATUS.md`

```sql
-- V9__verification_response.sql
create table verification_response (
    id                  uuid primary key,
    verification_id     uuid        not null references verification (id),
    outcome              text        not null check (outcome in ('MATCHES', 'DISCREPANCY', 'UNAVAILABLE')),
    raw_payload          jsonb       not null,
    received_at          timestamptz not null default now()
);
create index verification_response_verification_idx on verification_response (verification_id);
```

**Interfaces:**
- `MockVerificationService.resolve(verificationId)` — deterministic:
  hashes `(person_id, data_element)` into one of the three outcomes, so
  reruns are reproducible (same property `test_end_to_end.py` already
  relies on for the DMN model).
- `POST /api/program-requests/{id}/verifications/{verificationId}
/request` (`WORKER`, must hold the active `CASE_ASSIGNMENT` on that
  household — reuses Task 2's check) → synchronously resolves (it's a
  mock; nothing to actually wait on), writes `verification_response`,
  updates `verification.status`/`satisfied_on`, appends two
  `VERIFICATION_UPDATED` audit events (`stage: REQUESTED` then
  `stage: RECEIVED`).
- `GET /api/program-requests/{id}/verifications` (`WORKER`, same
  assignment check) → `verification.status` and, if resolved,
  `verification_response.outcome` — never `raw_payload`.

- [ ] **Step 1: `V9` migration + entity/repo.**
- [ ] **Step 2: `IntakeService` creates the outstanding verification
      row.** Test: submitting an application creates exactly one
      `verification` row with `data_element = 'INCOME'`,
      `status = 'OUTSTANDING'`.
- [ ] **Step 3: `MockVerificationService`, test-first.** Test: the same
      `(person_id, data_element)` always resolves to the same outcome
      across calls; the three outcomes are all reachable across a range
      of synthetic inputs (not degenerately always `MATCHES`).
- [ ] **Step 4: `VerificationController`, authorization test-first.**
      Test: a `WORKER` without the active assignment gets 403 on both
      endpoints (reusing Task 2's check — write this test alongside
      Task 2's own authorization tests conceptually, even though it
      lands in this task's commit). Test: `GET` never returns
      `raw_payload` in its JSON shape.
- [ ] **Step 5: Audit trail test.** Requesting a verification produces
      exactly two `VERIFICATION_UPDATED` rows in order, `stage`
      `REQUESTED` then `RECEIVED`, and the chain still verifies
      end-to-end afterward (`verify_chain()`).
- [ ] **Step 6: Full suite + commit.**

---

## Task 4: Airflow orchestration

**Files:**
- Create: `infra/airflow/dags/ies_pipeline_dag.py`
- Modify: `infra/docker-compose.yml` (+`airflow` service(s) —
  `LocalExecutor` needs one webserver+scheduler container against a
  metadata Postgres; reuse the existing `postgres` service with a
  separate database, per the same `infra/postgres/init/` pattern Task 12
  already uses for `ies_operational`/`ies_serving`)
- Modify: `infra/postgres/init/01-databases.sql` (+`airflow` database)
- Create: `data-platform/tests/test_airflow_dag.py`
- Modify: `docs/STATUS.md`

**Interfaces:**
- The DAG's tasks call the exact same entry points `make pipeline`
  already calls (`ies_data.ingestion.extract`,
  `dbt build` via `BashOperator`,
  `ies_data.serving.materialize`, `ies_data.reporting.provision_metabase`
  — Task 10/11/12's own functions/CLIs, per the design doc §2.6's stated
  default), scheduled `@hourly` (arbitrary but reasonable for a demo —
  a real deployment's cadence is a policy decision, not an engineering
  one).

- [ ] **Step 1: Airflow service in Compose**, metadata DB, `airflow db
      migrate` + admin user creation on first boot (standard Airflow
      Compose bring-up, per Airflow's own quick-start reference).
- [ ] **Step 2: `ies_pipeline_dag.py`** — four tasks (`extract`,
      `dbt_build`, `materialize`, `provision_metabase`), linear
      dependency matching `make pipeline`'s existing order, each a thin
      wrapper calling the real Python function (or `BashOperator` for
      `dbt build`, matching how `make pipeline` itself shells out).
- [ ] **Step 3: `test_airflow_dag.py`.** DAG-integrity test (imports
      cleanly, no cycles — Airflow's own standard test pattern) plus one
      real triggered run against the live Compose stack (`airflow dags
      test ies_pipeline dag <date>` or the Airflow REST API), asserting
      it completes and the serving database's row counts move the same
      way a manual `make pipeline` run already proves they do (Task 11's
      own test already established that baseline).
- [ ] **Step 4: Full suite + commit.**

---

## Task 5: Full medallion coverage

Six silver models, four gold marts (`mart_fairness_audit` deferred to
Phase 4 — design doc §2.4). Mirrors Task 10's existing silver-model
pattern (dedupe bronze to latest `_ingested_at` per natural key,
`meta: {classification: ...}` tags) and Task 11's gold-mart pattern.

**Files:**
- Modify: `data-platform/src/ies_data/ingestion/extract.py` (extend the
  7-table bronze source list to include `worker`, `case_assignment`,
  `verification`, `verification_response`, `audit_event` — currently
  narrower per Phase 1a's own stated scope, design doc references this)
- Create: `dbt/ies_warehouse/models/silver/dim_worker.sql`,
  `dim_program.sql`, `fct_application.sql`, `fct_verification.sql`,
  `fct_benefit_month.sql`, `fct_audit_event.sql` (+ each with a
  `.yml` schema file — `not_null`/`unique`/`relationships`/
  `accepted_values` tests, per CLAUDE.md's testing policy)
- Create: `dbt/ies_warehouse/models/gold/mart_processing_timeliness.sql`,
  `mart_payment_accuracy.sql`, `mart_worker_caseload.sql`,
  `mart_access_review.sql` (+ schema files)
- Modify: `docs/STATUS.md`

**Interfaces:**
- `mart_access_review`: one row per `CASE_VIEWED` event, joined to
  whether `in_assignment` was true — the direct consumer of Task 2's new
  payload field.
- `mart_worker_caseload`: active `case_assignment` count per worker.
- `mart_payment_accuracy`: placeholder shape for now (real payment-error
  computation needs Phase 4's QC assistant per roadmap §5) — this mart
  exists and is tested, but its business logic is intentionally thin in
  Phase 1b; state that explicitly in the model's own doc comment rather
  than pretending it's the full QC computation.
- `mart_processing_timeliness`: depends on Task 6's real `is_expedited`
  landing first for its standard column to mean anything — sequenced
  after Task 6 in execution even though it's listed under Task 5's
  broader scope; note the dependency, don't silently reorder the task
  table.

- [ ] **Step 1: Extend bronze source list**, extraction test updated for
      the new tables (same pattern as Task 10's own extraction test).
- [ ] **Step 2: Silver models, test-first** — each with its own `.yml`
      schema tests before the model SQL, same TDD order Task 10
      established.
- [ ] **Step 3: Gold marts, test-first**, `no_pii_in_gold` custom test
      re-run against all four new marts (it already scans
      `information_schema.columns` broadly, so no test change needed —
      just confirm it actually catches these new models too, don't
      assume).
- [ ] **Step 4: Full `dbt build`, full suite, commit.**

---

## Task 6: Reporting widened

Real `is_expedited` (already-existing column, never set — design doc
§2.6) plus the liquid-resources data gap that column needs to mean
anything.

**Files:**
- Create: `portal/src/main/resources/db/migration/
V10__household_resources.sql`
- Create: `portal/src/main/java/ies/portal/domain/ResourceRecord.java`,
  `repo/ResourceRecordRepository.java`
- Modify: `portal/src/main/java/ies/portal/intake/IntakeService.java`
  (accepts + persists liquid resources; computes `is_expedited` per 7
  CFR 273.2(i): gross income < $150 and liquid resources ≤ $100, or
  gross income + liquid resources < shelter cost)
- Modify: `portal/src/main/java/ies/portal/api/dto/IntakeRequest.java`
  (or wherever household-level fields live)
- Modify: `portal/web/src/pages/IntakePage.tsx` (one new field)
- Modify: `portal/src/test/java/ies/portal/intake/` tests
- Modify: `docs/STATUS.md`

```sql
-- V10__household_resources.sql
-- Household-level: liquid resources (bank accounts, cash) are countable
-- per case, not per member, unlike income/expense which are per person.
create table resource_record (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    resource_type        text        not null check (resource_type in ('CASH', 'BANK_ACCOUNT', 'OTHER_LIQUID')),
    amount               numeric(12, 2) not null check (amount >= 0),
    effective_from       date        not null,
    effective_to         date,
    created_at           timestamptz not null default now(),
    constraint resource_record_effective_range check (effective_to is null or effective_to >= effective_from)
);
create index resource_record_household_idx on resource_record (household_id, effective_from);
```

- [ ] **Step 1: `V10` migration, entity, repository.**
- [ ] **Step 2: Intake accepts liquid resources**, test-first — a new
      `IntakeRequest` field, persisted as a `resource_record`.
- [ ] **Step 3: `is_expedited` computation, test-first.** Table-driven,
      same style as the DMN scenarios: a household under both the
      income and resource thresholds is expedited; one over either isn't;
      the shelter-cost-comparison leg (income + resources < shelter
      cost) is its own case. This is intake-time SQL/Java logic, **not**
      a DMN change (design doc §2.6 — it doesn't affect the benefit
      calculation).
- [ ] **Step 4: `mart_processing_timeliness` becomes meaningful.** Now
      that `is_expedited` is real, the mart (Task 5) computes
      `decided_at - submitted_at` against 7 days if expedited, 30
      otherwise, and flags any determination that missed its standard.
      Test against a fixture with both an expedited and a standard
      request, one on-time and one late.
- [ ] **Step 5: Full suite + commit.**

---

## Task 7: Governance completed

PII tokenization (design doc §2.3 — not SSN, which is already
token-only; the real gap is name/DOB/address reaching silver in the
clear) plus the compliance-mapping doc.

**Files:**
- Create: `portal/src/main/resources/db/migration/
V11__pii_token_vault.sql`
- Create: `data-platform/src/ies_data/governance/tokenize.py`
- Modify: `dbt/ies_warehouse/models/silver/dim_person.sql` (stores
  tokens for `first_name`/`last_name`/`date_of_birth` instead of raw
  values)
- Modify: `dbt/ies_warehouse/models/silver/dim_household.sql` (same for
  address columns)
- Create: `data-platform/tests/test_tokenize.py`
- Create: `docs/design/compliance-mapping.md`
- Modify: `docs/STATUS.md`

```sql
-- V11__pii_token_vault.sql
create extension if not exists pgcrypto;  -- already enabled by V6, safe to repeat with IF NOT EXISTS
create table pii_token (
    token           text primary key,
    encrypted_value  bytea not null,
    value_type       text  not null check (value_type in ('NAME', 'DATE_OF_BIRTH', 'ADDRESS')),
    created_at       timestamptz not null default now()
);
revoke select on pii_token from public;
-- Grant is narrow and explicit at implementation time, per the design
-- doc's "detokenization is a separate audited call" requirement -- not
-- the same broad silver-read role.
```

**Interfaces:**
- `tokenize.py`'s `get_or_create_token(real_value, value_type) -> token`
  and `detokenize(token) -> real_value` both connect to the vault via
  DuckDB's `postgres` extension (the same mechanism `materialize.py`
  already uses for gold → serving, per Task 11's own STATUS.md row —
  reused, not reinvented).
- `dim_person`/`dim_household`'s silver build calls `get_or_create_token`
  per sensitive column during the model's Python pre-hook or a
  dbt-python model (decide which at implementation time based on what's
  cleanest against this project's existing dbt-duckdb setup; state the
  choice in the STATUS.md verification row).

- [ ] **Step 1: `V11` migration.**
- [ ] **Step 2: `tokenize.py`, test-first** — round-trip
      (`tokenize` then `detokenize` recovers the exact original value),
      the same real value always maps to the same token (idempotent, no
      duplicate vault rows), and a `detokenize` call on an unknown token
      raises rather than returning a null/default.
- [ ] **Step 3: Wire into `dim_person`/`dim_household`.** Test: after a
      full `dbt build`, `dim_person`'s `first_name`/`last_name`/
      `date_of_birth` columns hold token-shaped values, not the
      originals, and `detokenize()` against one recovers the exact
      operational-database value for that person.
- [ ] **Step 4: `compliance-mapping.md`.** NIST 800-53 control families
      (AC-3, AC-6, AU-*, SC-*) mapped to the specific mechanism in this
      repo that implements each — same "here's the code, not just the
      claim" standard the audit chain already sets. IRS Pub 1075-style
      treatment for the income-verification path from Task 3.
- [ ] **Step 5: Full suite + commit.**

---

## Task 8: Accessibility

**Files:**
- Modify: `portal/web/.eslintrc` (or flat config) — `eslint-plugin-
jsx-a11y` recommended rules
- Modify: `portal/web/package.json` (+`vitest-axe`)
- Modify: `portal/web/src/test/*.test.tsx` (existing tests for
  `IntakePage`, `WorkerCasesPage`, `CaseDetailPage` gain an axe
  assertion each)
- Modify: `docs/STATUS.md`

- [ ] **Step 1: Lint rule.** `npm run lint` (or `typecheck` script,
      whichever already runs a11y-adjacent checks — confirm current
      script names) fails on a deliberately-broken fixture (an `<img>`
      with no `alt`) before passing on real code, proving the rule is
      live, not just installed.
- [ ] **Step 2: `vitest-axe` on the three pages**, test-first — each
      existing render test gains `expect(await axe(container)).toHaveNo
Violations()`, and any real violation it finds gets fixed (not
      suppressed) before this task is done.
- [ ] **Step 3: Manual keyboard-nav check**, recorded in the STATUS.md
      verification row same as any other manual-only check in this
      project (e.g. Phase 5's photo-picker note) — tab order through the
      intake form and case list, confirmed reachable/operable without a
      mouse.
- [ ] **Step 4: Full suite + commit.**

---

## Task 9: Observability

**Files:**
- Modify: `infra/docker-compose.yml` (+`jaeger`, `prometheus`,
  `grafana`)
- Create: `infra/observability/prometheus.yml`,
  `infra/observability/grafana-provisioning/`
- Modify: `portal/pom.xml` (+`micrometer-tracing-bridge-otel`,
  `opentelemetry-exporter-otlp`)
- Modify: `portal/src/main/resources/application.yml` (OTLP exporter
  endpoint pointing at Jaeger, `management.tracing.sampling.probability:
1.0` for a demo)
- Create: `data-platform/src/ies_data/observability/tracing.py`
- Modify: `data-platform/src/ies_data/ingestion/extract.py`,
  `dbt` build wrapper, `serving/materialize.py`,
  `reporting/provision_metabase.py` (each pipeline stage wrapped in a
  span)
- Create: `data-platform/tests/test_observability.py`
- Modify: `docs/STATUS.md`

- [ ] **Step 1: Jaeger/Prometheus/Grafana services in Compose.**
- [ ] **Step 2: Portal auto-instrumentation.** Spring Boot's OTel starter
      needs no manual span code for HTTP/JDBC — confirm by making one
      real request against the running stack and checking Jaeger's UI
      for a trace with the expected spans (portal → Postgres), the same
      "verify against the real thing" standard as Task 11's Metabase
      provisioning check.
- [ ] **Step 3: Data-platform manual spans.** `tracing.py`'s
      `init_tracer()` + a `@traced` decorator (or explicit
      `with tracer.start_as_current_span(...)`) around each of the four
      pipeline stages; run `make pipeline` once against the real stack
      and confirm four real spans land in Jaeger.
- [ ] **Step 4: `test_observability.py`.** Hits Jaeger's query API
      (`GET /api/traces?service=...`) after a real portal request and a
      real pipeline run, asserting at least one trace exists for each —
      same shape as `test_stack_smoke.py`'s existing real-endpoint
      checks, not a mock.
- [ ] **Step 5: Full suite + commit.**

---

## Task 10: Reference Terraform for Azure

Not applied by default — reference only, per roadmap §3.7/§7's Azure
Government framing. Written to be `usgovcloud`-compatible, documented,
never actually run against a live subscription in this project.

**Files:**
- Create: `infra/azure/main.tf`, `variables.tf`, `outputs.tf`,
  `providers.tf`
- Create: `infra/azure/README.md` (the `usgovcloud` endpoint/provider-
  alias swap, called out explicitly, matching roadmap §3.7's own framing)
- Modify: `docs/STATUS.md`

**Resources modeled** (matching this repo's own components):
Resource group; Azure Database for PostgreSQL Flexible Server (the
operational + serving stand-in); Azure Container Apps or AKS for the
portal API/web and Airflow; Key Vault (the Secrets row's real-production
target, per the tradeoffs doc); Azure Monitor (the Observability row's
real-production target).

- [ ] **Step 1: Write the `.tf` files.** No `terraform apply` — this
      task's "test" is `terraform validate` and `terraform fmt -check`,
      run in CI (a new lightweight job, not a Compose-based one).
- [ ] **Step 2: `README.md`** stating plainly what's modeled, what's
      deliberately absent (a real subscription, real state backend,
      real secrets), and the exact `usgovcloud` swap.
- [ ] **Step 3: CI job.** `.github/workflows/ci.yml` gains a `terraform`
      job running `validate`/`fmt -check` only.
- [ ] **Step 4: Full suite + commit.**

---

## Phase 1b definition of done

- [ ] `make test`, `make lint`, `make e2e` all pass from a clean clone,
      now authenticating through real Keycloak tokens.
- [ ] A `WORKER` with no `CASE_ASSIGNMENT` on a household gets 403; a
      `SUPERVISOR` viewing the same household gets 200 and a
      distinctly-logged `CASE_VIEWED` event.
- [ ] The mock verification flow completes end to end with a real audit
      trail, and its raw response is unreachable outside an active case
      assignment.
- [ ] Airflow runs the real pipeline on its own schedule, observable in
      its UI, without `make pipeline` needing to be run by hand.
- [ ] `dbt build` produces all ten silver models and nine gold marts
      (five from Phase 1a/1b's Task 5 plus `mart_fairness_audit` still
      correctly absent until Phase 4), all tests green.
- [ ] A determination for an expedited household is flagged as such for
      a real, data-backed reason, and `mart_processing_timeliness`
      reports against the correct 7- or 30-day standard.
- [ ] `dim_person`/`dim_household` carry tokens, not raw PII, in silver;
      detokenization works and is itself audited.
- [ ] The three main portal pages are axe-clean.
- [ ] A real request and a real pipeline run both produce visible traces
      in Jaeger.
- [ ] `terraform validate`/`fmt -check` clean in CI.
- [ ] `docs/STATUS.md`, `CLAUDE.md`, and `README.md` all reflect reality.

## Deferred out of Phase 1b, on purpose

Recorded so a later session doesn't read an absence as an oversight:
identity *proofing* (Keycloak authenticates accounts, doesn't verify a
human's real-world identity); true sensitive-case sealing with an
override workflow (this phase only flags and logs); periodic access
recertification; a real (non-mock) external verification counterparty;
`mart_fairness_audit` (Phase 4, alongside fraud-triage); incremental dbt
materialization; a real data catalog; CDC/Debezium ingestion; multi-
environment promotion; and any actual Azure deployment. Every one of
these is Phase 4/5 or explicitly out of this portfolio project's scope
per the tradeoffs doc.
