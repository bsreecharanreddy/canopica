# IES — Phase 1b Hardening: Design Decisions

Status: approved
Date: 2026-08-22
Expands: `docs/design/2026-08-21-full-system-and-phased-roadmap.md` §5's
"Phase 1b — hardening" bullet list and §3.4's domain model. That doc says
*what* Phase 1b covers (identity, row-level authorization, external
verification, orchestration, full medallion coverage, governance,
accessibility, observability, reference Terraform — ten tasks, tracked in
`docs/STATUS.md`). This doc resolves the *how* for the five points that
were still genuinely open, plus states a handful of lower-stakes defaults
for the record. It does not replace the roadmap doc's higher-level framing
— read that first if the "why" behind any of this is unclear.

This is a design doc, not an implementation plan. No DDL, no exact
endpoint paths, no migration numbering — that's `docs/plans/`'s job, in a
plan written from this doc, per CLAUDE.md's brainstorm → dated doc →
approval → implementation-plan convention. This is the "approval" step.

**Correction (2026-08-22, same day):** §2.1 and §2.2 as first written
assumed `worker`, `case_assignment`, and `verification` needed to be
*created* in Phase 1b. Checking the actual shipped schema (not just the
roadmap doc) after writing the first draft found all three already exist
— Phase 1a's Task 2 deliberately over-built the schema
(`V1__core_entities.sql`'s own comment: "what makes caseload-scoped
authorization possible at all *in Phase 1b*"), then never wired any of it
into runtime behavior. Same for `program_request.is_expedited` (§2.6) and
`audit_event`'s `VERIFICATION_UPDATED` type. Rewritten below to build on
what's actually there instead of duplicating it — the exact "verify
before recommending" discipline this project already applies everywhere
else, applied to my own draft.

## 1. Scope recap

Ten tasks, per `docs/STATUS.md`'s Phase 1b table. This doc resolves the
decisions behind Tasks 1, 2, 3, 5, and 9. Tasks 4, 6, 7, 8, and 10 either
already had enough detail in the roadmap doc to proceed directly to an
implementation plan, or are addressed below as short stated defaults
(§2.6) rather than full decisions, since they didn't have a genuine fork.

## 2. Decisions

### 2.1 Caseload & row-level authorization (Task 2)

**Already built, unused:** `worker` (`id`, `full_name`, `email`, `role`
— the `CHECK` constraint already allows `WORKER` / `SUPERVISOR` / `ADMIN`)
and `case_assignment` (`household_id`, `worker_id`, effective-dated) both
exist since Phase 1a's `V1__core_entities.sql`, with JPA entities
(`Worker`, `CaseAssignment`) and `CaseAssignmentRepository` already
written. Nothing in Phase 1a's runtime code ever creates a `worker` row
or a `case_assignment` row — `decided_by`/`actor_id` everywhere today
store the raw role string (`"WORKER"`), not a `worker.id`. Task 2's job in
Phase 1b is **activating** this schema, not creating it: no new migration
for the base tables, no new role value.

**What genuinely is new:** a way to map a real Keycloak-authenticated
identity to a `worker` row (Task 1 needs to add a `keycloak_subject text
unique` column to `worker` via a migration, populated from the token's
`sub` claim on first login) and, on `household`, `is_sensitive boolean
not null default false` + `sensitive_reason text` (neither exists today).

`CASE_ASSIGNMENT` keys off `household_id`, matching the case-record model
already established when `household` gained a mailing address in Phase
1a's Task 2. **`CASE_VIEWED`'s existing subject is `program_request_id`,
not `household_id`** (`WorkerCaseController`'s
`auditService.append(AuditEventType.CASE_VIEWED, ..., "program_request",
id, Map.of())`) — the authorization check needs the join
`program_request → application → household → case_assignment`, since
assignment is household-scoped but the event that already exists is
request-scoped. Worth being exact about this rather than assuming a
direct id match.

**Assignment is explicit, not implicit-by-county.** A `CASE_ASSIGNMENT`
row is the source of truth for "who can see this case" — never a role
check, never a county match. Populating it is auto-claim-on-first-touch:
the first worker to open or act on a household with no existing
assignment becomes the assigned worker (a `CASE_ASSIGNMENT` row is
written as a side effect, no separate queue-assignment UI needed for
Phase 1b). A `SUPERVISOR` can reassign explicitly — the role value
already exists in the schema, so this is new controller/service logic
against an existing column, not a new one.

Rationale for explicit over implicit: county-based implicit scoping can't
actually demonstrate the access-review story the roadmap centers on
("the characteristic real-world breach... is an authorized worker viewing
a case they have no business reason to touch" — roadmap §3.3). Auto-claim
keeps the Phase 1b build small — no assignment-queue UI — while still
being backed by a real table, not a role string.

**A `SUPERVISOR` can view any household**, assigned or not. The
authorization check therefore isn't binary allow/deny — a `WORKER`
viewing a household they're not assigned to is a **denied** action (403,
same shape as the existing CUSTOMER-hits-WORKER-endpoint case from Task
7); a `SUPERVISOR` viewing any household is **allowed but logged
distinctly**: `CASE_VIEWED`'s payload (currently written as `Map.of()` —
an empty map, a one-line change to extend) gains an `in_assignment:
boolean` field, so `mart_access_review` (Task 5) can filter for exactly
the supervisor-viewed-outside-assignment rows the roadmap's row calls
out. No new audit event type — reuses what Task 7 already writes.

**Sensitive-case flagging** is the new `is_sensitive`/`sensitive_reason`
pair on `household`, settable only by `SUPERVISOR`. Flagging doesn't
block access — every role that could already see the case still can — it
raises the audit signal: a `CASE_VIEWED` event against a flagged
household is what a real access-review process would triage first. True
sealing (blocking access outright, requiring an override workflow) is
explicitly not built — see tradeoffs doc's Authorization row, refined
below (§3).

### 2.2 Mock external verification interface (Task 3)

**Already built, unused:** the `verification` table exists since Phase
1a's `V2__intake_records.sql` — `program_request_id`, `data_element`
(`IDENTITY` / `RESIDENCY` / `INCOME` / `SHELTER_COST` / `MEDICAL_EXPENSE`
/ `DISABILITY` / `HOUSEHOLD_COMPOSITION`), `status` (`OUTSTANDING` /
`RECEIVED` / `WAIVED`), `due_on`, `satisfied_on` — with a `Verification`
JPA entity and `VerificationRepository` already written. This already is
the roadmap's VERIFICATION entity ("tracks each outstanding data element,
its due date, and how it was satisfied" — §3.4.1). Nothing in Phase 1a
ever inserts a row into it. **Task 3 does not create a new table for
this** — it activates `verification` (intake creates a row per applicant
with `INCOME` verification outstanding) rather than inventing a
parallel `verification_record` table, correcting this doc's first draft.

Also already reserved: `audit_event`'s `event_type` `CHECK` constraint
already includes `VERIFICATION_UPDATED` (`V6__audit_event.sql`), unused
by any Phase 1a code path. **Reuse it for both the request and the
received-response events**, distinguished by a `stage` field in the
event's JSON payload (`REQUESTED` / `RECEIVED`) — smaller migration
footprint than adding two brand-new `CHECK` values, and it's what that
value already looks reserved for.

Synchronous REST, not `pgmq`. The roadmap's async-messaging decision row
names document-intake, correspondence, and fraud-triage as `pgmq`
consumers (Phase 3/4); verification isn't among them, and a request/reply
lookup doesn't benefit from decoupling the way a long-running
classification or dispatch job does.

**What genuinely is new:** a `verification_response` table — the mock
interface's raw response, which `verification` itself has no field for
(it's a status/tracking row, not a payload store). Columns: a reference to
the `verification` row, an `outcome` (`MATCHES` / `DISCREPANCY` /
`UNAVAILABLE` — kept off `verification.status` itself, so its existing
`OUTSTANDING`/`RECEIVED`/`WAIVED` `CHECK` constraint doesn't need
touching), and the raw mock payload. The mock responder is deterministic
— it derives its canned outcome from a hash of the input (person +
verification type), so the same household always gets the same mock
result across runs, the same reproducibility property the DMN model
already has for determinations. Resolving a `verification` row (setting
`status = 'RECEIVED'`, `satisfied_on`) is what actually happens to the
existing table; the new table only carries what's genuinely new.

**FTI-style safeguards, made concrete rather than asserted:**

- Every request and response is a `VERIFICATION_UPDATED` audit-chain
  event (see above), not just an application log line — the same "verify
  it, don't just log it" standard the hash-chained audit log already
  holds everything else to.
- `verification_response` is readable only by a role holding an *active
  `CASE_ASSIGNMENT`* on that household — reusing §2.1's authorization
  model rather than inventing a second one.
- No raw response value is ever surfaced to `CUSTOMER` role, only
  `verification.status`.

The sync-vs-batch fidelity gap this implies (real verification interfaces
lean batch/SFTP, not request/reply REST) is already stated in the
tradeoffs doc's Interfaces tier "Transport" row — no new tradeoffs-doc
entry needed for that part; §3 below only tightens the existing "External
verification" row's description to match this concrete shape.

### 2.3 PII tokenization (Task 7, feeds Task 5's silver layer)

**Not in scope: SSN.** `person.ssn_token` has been a token with no real
underlying value since Phase 1a's Task 2 — its own column comment says so
("The real value never exists in this system; the token is what the
warehouse ever sees"). There is nothing to vault or detokenize for it;
it's already solved, by a different and simpler mechanism (never storing
the real value at all) than the vault below.

**In scope:** `first_name`, `last_name`, `date_of_birth` on `person` and
the address columns on `household` — real values, genuinely collected,
carried into silver in the clear today (`dim_person`, per Task 10's
`meta: {classification: SENSITIVE}` tagging), protected only by gold's
`no_pii_in_gold` build-time test and column-level access conventions.
That's enough to keep PII out of marts, but not enough to call it
"tokenized" — anyone with silver access still sees the raw value.

**Decision:** a `pii_token` vault table — `token` (opaque, what silver
actually stores in place of the real value), `encrypted_value` (via
Postgres's built-in `pgcrypto`, not a new dependency), `value_type`. Every
sensitive column silver models currently store in the clear switches to
storing the token instead. Detokenization — recovering the real value —
is a **separate, explicit, audited call**, not a normal column read: it
requires the vault table's own narrow RLS grant (not the general silver
read role), and every detokenization is itself an audit-chain event.

This is marked **substituted (~)**, not same-shape, in the tradeoffs doc
(§3 below) — a real tokenization product runs as an out-of-band service
with its own credential and often HSM-backed keys, so compromising the
application database doesn't also compromise the token vault. Here, the
vault lives in the same Postgres instance and the same failure domain as
the data it protects — the same shape of compromise §4.11's `pgmq`
tradeoff already accepts for messaging, applied to PII instead of queues.
Worth stating plainly rather than calling it equivalent to a real vault.

**Correction (2026-08-22, found implementing Task 7):** this section's
opening premise — "carried into silver in the clear today" — turned out
to be wrong, the same class of error §2.1/§2.2's corrections already
caught for a different pair of assumptions. Checking `dim_person.sql` and
`dim_household.sql` (both Task 10, Phase 1a) directly: `dim_person`
already stores `sha256(lower(first_name || '|' || last_name))` as
`name_hash` (a one-way hash) and `extract(year from date_of_birth))` as
`birth_year` only — never the full date. `dim_household` already drops
`address_line1`/`address_line2`/`city` entirely, keeping only
`county`/`state`/`zip_code`. Neither model has been touched since Task 10.

The real gap isn't "raw PII in silver" — it's that a **one-way hash
forecloses the one thing a token vault is actually for**: recovering the
real value under an explicit, audited need (correcting a misspelled name,
an access-review investigation). `birth_year`/`county`/`state`/`zip_code`
are lossy minimizations, already a stronger posture than a reversible
token would be, and no planned consumer has a legitimate need to recover
the exact original DOB or street address from the warehouse.

**Revised decision:** build the `pii_token` vault exactly as designed
above, but apply it only to upgrade `dim_person`'s `name_hash` (irreversible)
into a `name_token` (reversible, vault-backed, audited detokenization).
Leave `birth_year` and `dim_household`'s address handling untouched — they
already satisfy this section's real intent through a different, arguably
stronger mechanism (data minimization at the source) than tokenization
would add. `docs/design/compliance-mapping.md` (also this task) records
this explicitly rather than silently narrowing scope.

### 2.4 `mart_fairness_audit` deferred to Phase 4

§3.4.2 lists `mart_fairness_audit` under Phase 1b's "full medallion
coverage" (Task 5), but the roadmap's own fairness-audit CI gate (§3.3)
is scoped to "the rules engine *and* the fraud-triage model" — and
fraud-triage doesn't exist until Phase 4. Building the mart now would
mean shipping a mart with one axis of comparison and nothing to add to it
until two phases later.

**Decision:** Task 5 builds the other five gold marts named in §3.4.2
(`mart_processing_timeliness`, `mart_determination_outcomes` — already
built in Phase 1a — `mart_payment_accuracy`, `mart_worker_caseload`,
`mart_access_review`). `mart_fairness_audit` moves to Phase 4, built
alongside fraud-triage so it has both axes to compare from day one. The
roadmap doc's §3.4.2 table and Phase 4 bullet list should get a one-line
note reflecting this the next time either section is touched — not a
rewrite now, since the content is still correct, just under-specified on
timing.

### 2.5 Observability stack (Task 9)

Lightweight and self-hosted, consistent with the project's "$0, `docker
compose up`" constraint (tradeoffs doc §5): **Jaeger** (all-in-one image)
for traces, **Prometheus + Grafana** for metrics. Not a heavier
collector/Tempo/Loki stack — that's real production shape (see tradeoffs
doc's Observability row, already scoped to Azure Monitor/Splunk as the
production equivalent), but it's more services than a demoable local
Compose stack needs to prove the instrumentation pattern works.

OpenTelemetry SDK instrumentation goes into both the portal API and the
data-platform pipeline jobs — the roadmap's "OpenTelemetry across API +
pipeline" line, taken literally rather than API-only.

### 2.6 Stated defaults (not forks — recorded for completeness)

- **Airflow executor:** `LocalExecutor`. `CeleryExecutor` needs
  Redis/RabbitMQ, infrastructure this single-host Compose demo has no
  other use for. The DAG calls the same Task 10/11/12 Python
  functions/CLIs `make pipeline` already calls — Airflow becomes the
  scheduled path, `make pipeline` stays the manual/dev path, and neither
  can drift from the other since both run the same underlying code.
- **Keycloak realms:** the worker realm is directly-provisioned test
  users (`WORKER`, `SUPERVISOR` roles), not real SSO/IdP brokering —
  brokering to a real enterprise IdP is what "SSO simulation" stands in
  for conceptually, not something to actually stand up a second IdP to
  demonstrate.
- **Expedited (7-day) SNAP processing — already-built, unused schema,
  plus a real gap found while resolving this:**
  `program_request.is_expedited` (boolean, default `false`) has existed
  since Phase 1a's `V2__intake_records.sql` ("SNAP's federal processing
  standards: 30 days normal, 7 days expedited... stored per request
  because expedited status is determined per request") — nothing has ever
  set it to `true`. The gap: real expedited eligibility (7 CFR 273.2(i))
  needs a household's
  liquid resources, which Phase 1a's intake never collects (the asset
  test is explicitly listed as unmodeled in README's "Honest
  limitations"). Populating the existing column without that data would
  just be wrong, not a simplification. Decision: Task 6 adds one small
  intake field — liquid resources, effective-dated like income/expense
  records already are — so `is_expedited` gets computed for real. This
  does **not** touch the DMN model: expedited-vs-standard changes which
  *processing-time standard* applies, not the benefit calculation itself.
- **`test_end_to_end.py` / `docs/demo.md` need a real adaptation once
  `X-IES-Role` goes away** — Task 1 replaces the header with actual
  Keycloak tokens, so the e2e test needs to fetch a real token from
  Keycloak's token endpoint for a seeded test user, the same "hit the
  real thing" standard Phase 1a's own e2e test already holds everything
  else to (no mocking the auth layer just because it's inconvenient to
  set up for real).

## 3. Tradeoffs doc — refinements this unlocks

Recorded here so the actual edits (next, in the same commit as this doc)
have a stated reason instead of appearing as a driveby diff:

- **Data tier:** new row, "PII protection (silver tokenization)" —
  `pgcrypto`-backed `pii_token` vault vs. a real tokenization
  product/HSM-backed vault, fidelity **~**, with a new §4.15 entry
  explaining the shared-failure-domain cost (§2.3 above).
- **Interfaces tier, "External verification" row:** tightened to name
  the concrete mechanism (synchronous REST, deterministic canned
  responses, audit-chain-logged) instead of the current generic "mock
  interface... with FTI-style safeguards genuinely applied." Fidelity
  mark unchanged (**~**) — this is a specificity edit, not a new
  tradeoff.
- **Application tier, "Authorization" row:** tightened to name
  `CASE_ASSIGNMENT` and clarify that sensitive-case handling here is
  flag-and-log, not true sealing/blocking — the existing "What would
  change" cell (recertification workflow) still holds, plus real sealing
  with an override workflow.
- **Platform tier, "Observability" row:** tightened from generic "local
  collector" to the concrete Jaeger + Prometheus/Grafana shape (§2.5).

## 4. What this doc does not settle

Tasks 4 (Airflow DAG structure beyond executor choice), 6 (the rest of
"reporting widened" beyond the expedited-processing data gap above), 7
(governance beyond tokenization — the `compliance-mapping.md` control
mapping itself), 8 (accessibility), and 10 (reference Terraform) don't
have open forks worth a brainstorm pass — the roadmap doc and existing
Phase 1a patterns (e.g., `dbt` test conventions, existing CI structure)
are enough to go straight to an implementation plan for those. That plan
— file-by-file, task-by-task, mirroring
`docs/plans/2026-08-21-phase-1a-implementation-plan.md`'s shape — is the
next step, once this doc is recorded.
