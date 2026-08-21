# IES — Implementation Status

**Read this file first.** It is the authoritative record of where the
implementation stands against the full plan. It is updated and committed
*in the same commit* as the work it describes, so it never drifts and
always survives a closed session, a new machine, or a fresh pair of eyes.

Last updated: **2026-08-21**

---

## Current position

**Design phase complete. Phase 1a planned; implementation not yet started.**

All three design docs are written, reviewed, and committed. The design has
been through one full review pass (2026-08-21) which added the domain
model, effective dating, and tamper-evident audit design, changed the DMN
runtime and reporting toolchain, and split Phase 1 into 1a/1b.

The Phase 1a implementation plan is written and committed:
`docs/plans/2026-08-21-phase-1a-implementation-plan.md` — file-by-file, 13
tasks, each with its own tests, its own commit, and its own STATUS update.
It also pins the toolchain versions this phase builds against and records
two environment prerequisites (Docker Desktop running; `uv` installed).

**Next action:** Task 9 — synthetic applicant generator (ACS PUMS–driven).

---

## Verification log

Every row records a full-suite run, not a partial one.

| Date | Scope | Result |
|---|---|---|
| 2026-08-21 | Task 8 -- `npm run typecheck && npm test` (web, 4 files/7 tests), `make test` (Java 41, Python 4), `make lint` | All green. Web: +6 tests over Task 1's single app-shell smoke test -- intake submission shows the confirmation reference number and surfaces a field-level `role="alert"` on a rejected submission (both from the plan's own test spec, run verbatim), the worker case list renders an accessible table (`aria-label="Cases"`) with column headers and a per-row link, and the case-detail page shows a determination's outcome/benefit/reason code/policy-parameter-version, re-renders with a new determination on "Run determination" without losing the prior one (append-only history, proven at the UI layer the same way Task 7 proved it at the API layer), and its collapsible trace panel lists each DMN decision name/value in evaluation order once expanded. One React app with role-gated views via `react-router-dom` (new dependency) and a `RoleContext`/`X-IES-Role`-header switch standing in for login, mirroring `HardcodedRoleFilter` on the client -- Phase 1b's real auth swap replaces this one context, not any page. `src/api/types.ts` hand-mirrors Task 7's Java DTOs; `src/api/client.ts` wraps `fetch`, attaches the role header, and turns a `400 {errors: [...]}` body into a typed `ApiValidationError`. Two real bugs found, not just the new tests: (1) `window.localStorage` is unavailable in this Node/jsdom/Vitest combination (`--localstorage-file` not provided) -- reading it eagerly at module-import time in `client.ts` threw synchronously and crashed the whole Vitest worker before any test in the file could run, cascading into three unrelated "worker timeout" failures that looked like nothing to do with localStorage until traced back; fixed by guarding every access in try/catch rather than a bare `typeof window` check, which doesn't protect against localStorage itself being missing/blocked. (2) `CaseDetailPage.test.tsx`'s own first draft asserted `screen.findByText(/eligible/i)`, which matched both the outcome text ("Eligible") and the reason code value ("ELIGIBLE") -- a real, sensible UI ambiguity, not a component bug; fixed by asserting the exact, case-sensitive string "Eligible" instead of a case-insensitive regex. |
| 2026-08-21 | Task 7 -- `make test` (Java 41 tests, portal now includes the API layer), `make lint` | All green. Java: +10 tests over Task 6 -- intake contract (submitting creates exactly one program_request + one APPLICATION_SUBMITTED audit event, rejects an empty `members` list with `errors[0].field == "members"`, rejects an income record whose effectiveTo precedes effectiveFrom), the worker case-view read surface (the caseload list carries head name/status/latest-determination summary, the case-detail endpoint returns determination history newest-first and appends CASE_VIEWED, the trace endpoint returns the same decision names the DMN model defines), and authorization (CUSTOMER gets 403 from a WORKER-only endpoint, a missing or unrecognized `X-IES-Role` header gets 401). New `spring-boot-starter-security` dependency; `HardcodedRoleFilter` sets the role header itself as the authenticated principal name (no other identity concept exists in Phase 1a), so `Authentication#getName()` is what every write endpoint records as `decided_by`/`actor_id` -- Phase 1b's Keycloak swap replaces one filter, not any controller. Also finally wired up `ies.timezone` (declared in application.yml since Task 1, unused until now) into a `Clock` bean, since intake is the first place "today" as a civil-calendar concept actually matters. Three real bugs found by the full-suite run, not just the new tests: (1) `@PathVariable UUID id` failed at request time with "Ensure the compiler uses the '-parameters' flag" -- this project's root pom never extended `spring-boot-starter-parent`, which is what normally sets that flag by default; fixed once, project-wide, via `maven.compiler.parameters=true` in the root pom rather than naming every path variable explicitly. (2) `HardcodedRoleFilter` NPE'd on a request with no `X-IES-Role` header at all (not just an unrecognized one) -- `Map.of(...).get(null)` throws rather than returning null, unlike `HashMap`; fixed with an explicit null guard before the lookup. (3) `IntakeControllerTest`'s own first draft asserted an absolute `count(*) from program_request` of 1, copied directly from the plan's example test -- passed in isolation but failed under `make test`'s full run (count was 10) because `AbstractPostgresTest`'s Postgres container is a JVM-wide singleton shared with every other test class's fixtures; fixed to scope the assertion to the specific `programRequestId` the test's own submission returned, the same "find by id, not by count/position" pattern `WorkerCaseControllerTest` used from the start for the same reason. |
| 2026-08-21 | Task 1 — `make test`, `make lint` (Java `./mvnw verify`, web `npm test`/`npm run typecheck`, Python `uv run pytest`/`ruff`/`mypy --strict`) | All green. Java: 1 test (context loads). Web: 1 test (app shell renders). Python: 2 tests (Settings config). No integration/e2e tests yet — no database, no Compose stack exists until Task 2 onward. |
| 2026-08-21 | Task 2 — `make test`, `make lint` (portal now runs 9 Testcontainers tests against a real Postgres 16 instance) | All green. Java: 9 tests — schema migration (V1/V2 apply, every Phase 1a table exists, every effective-dated table carries both date columns, household carries a mailing address), effective-dating/benefit-month constraint enforcement, and as-of query correctness for income_record. Web/Python unchanged from Task 1. Domain scope grew mid-task: `household` gained a mailing address (address_line1/2, city, state, zip_code) after clarifying that `household` is IES's case record — one HOH, many members via household_member, one or more applications over the case's life (including renewals) — and a case needs an address, which nothing in the schema carried yet. |
| 2026-08-21 | Task 3 — `make test`, `make lint` (portal now runs 17 Testcontainers tests) | All green. Java: +8 tests over Task 2 — as-of parameter resolution across the FY2025/FY2026 boundary (exact, not off-by-one), size-scoped vs. scalar parameter distinction, missing-size and missing-date rejection, and database-enforced immutability (UPDATE/DELETE on published parameter sets refused). FY2025 and FY2026 SNAP figures (max allotments, standard deductions, gross/net income limits, excess shelter cap, minimum benefit) verified directly against USDA FNS's published COLA memos before seeding — see docs/design/policy-parameter-provenance.md for citations; statutory figures (20% earned-income deduction, $35 medical threshold, 50% shelter share, 30% benefit reduction, 2-person minimum-benefit cutoff) cited to 7 U.S.C./7 CFR since they aren't in the COLA memos. One regression caught and fixed: Task 1's `IesPortalApplicationTest` excluded JPA/DataSource autoconfiguration (valid when written, before any database existed) and broke once Task 3 added a `@Component` requiring JPA repositories — converted to extend `AbstractPostgresTest` like every other test since Task 2, consistent with that class's own doc comment. |
| 2026-08-21 | Task 6 -- `make test` (Java 31 tests, Python 4 tests incl. 2 real Postgres-integration), `make lint` | All green. Java: +4 tests -- the chain's first row links from the zero-hash, every row links to its predecessor, UPDATE/DELETE both refused with "append-only", and every real determination appends exactly one DETERMINATION_MADE event carrying the policy parameter version in its payload. Python: a new `verify_chain()` CLI/library (`ies_data.audit.verify_chain`) plus two integration tests against a Postgres instance running the portal's *actual* Flyway migrations (via the `flyway/flyway` Docker image, not a copied-SQL approximation) -- proves an untampered 5-row chain verifies, and that a superuser directly disabling the trigger and editing a row is still caught (the verifier detects what no application-level control could have prevented). New CI job `audit-chain` runs this against GitHub Actions' own Docker daemon. One environment-specific issue found and fixed, not a code bug: Testcontainers-Python's Ryuk reaper container fails to start on this machine's Docker Desktop for macOS ("error while creating mount source path ...docker.sock: operation not supported") -- a known Docker-Desktop-macOS quirk affecting testcontainers-python specifically (the Java-side Testcontainers tests are unaffected). Worked around via `TESTCONTAINERS_RYUK_DISABLED=true`, scoped to the Makefile's Python test invocation only (not CI, which doesn't hit this on Linux runners) -- documented in `tests/conftest.py`'s module docstring so a future session recognizes it immediately rather than re-diagnosing. Also switched off the deprecated `testcontainers.postgres` import path to `testcontainers.community.postgres` while touching this file. |
| 2026-08-21 | Task 5 — `make test`, `make lint` (portal now runs 27 Testcontainers tests) | All green. Java: +10 tests over Task 4 -- fact assembly (as-of exclusion of not-yet-effective income, inclusion of later-effective income, elderly-by-age-60 and disability-record detection, SSI-driven categorical eligibility), determination persistence (determination + trace both written, append-only enforced, a denial stores a zero benefit and the correct reason code), and the exact property CLAUDE.md's testing policy names for the rules engine: an old determination re-run against its own stored parameter-set version reproduces its original answer even after both the household's income and the fiscal year have since moved on, plus a determination made on/after October 1 picks up the new fiscal year. All passed on the first real run -- no logic bugs, only two known Jackson/Hibernate wiring points handled up front: `@JdbcTypeCode(SqlTypes.JSON)` on the two jsonb-backed trace columns (plain String mapping fails Hibernate's ddl-auto=validate against a jsonb column), and SnapPolicyParameters resolution split into a shared `buildFromSet` helper so reproduction can pin to a stored parameter_set_id instead of re-resolving by "today's" date. |
| 2026-08-21 | Task 4 — `./mvnw -pl rules-engine test` (rules-engine module) | All green: 12 tests, 0 failures. 2 DMN model sanity tests (compiles clean, every named decision appears in the trace) + 9 table-driven SNAP scenarios (gross/net income pass/fail, each deduction in order, categorical eligibility, elderly/disabled uncapped shelter deduction, minimum-benefit floor, "computes to zero is a denial not a $0 award") + 1 as-of-date-correctness test (same facts, two parameter versions, different benefits -- proves parameters are injected, not baked in). All 12 passed on the first real run after two build-time fixes (Class-vs-ClassLoader argument to kie-dmn's classpath loader; a missing JUnit import) and one XML-syntax fix (an illegal double-hyphen inside an XML comment, unrelated to DMN semantics) -- no arithmetic mismatches, meaning the hand-computed expected values and the fifteen-decision DMN model agreed on every scenario. `make test`/`make lint` (full project) also green. |

---

## Phase 1a — Walking skeleton

The thinnest path that touches every layer and produces a real, correct,
auditable determination. Demoable on completion.

Task breakdown is the definitive one from
`docs/plans/2026-08-21-phase-1a-implementation-plan.md`; read that plan for
each task's files, interfaces, and test steps.

| # | Task | Status |
|---|---|---|
| 1 | Repo scaffolding, Maven/uv/Vite toolchains, CI skeleton | Done — 6af08cf |
| 2 | Operational schema, effective-dated (Flyway + Testcontainers) | Done |
| 3 | `policy_parameter_set` — effective-dated SNAP parameters + as-of resolver | Done |
| 4 | DMN decision tables on Drools/KIE, table-driven scenarios | Done |
| 5 | Determination service — persisted determination + DMN trace | Done |
| 6 | Hash-chained audit log + CI chain-verification job | Done |
| 7 | Portal API — intake + worker case view (roles hardcoded) | Done |
| 8 | React UI — intake form, case list, trace panel | Done |
| 9 | Synthetic applicant generator (ACS PUMS–driven) + loader | Not started |
| 10 | Ingestion to Delta bronze + dbt silver/gold with tests | Not started |
| 11 | Reporting — serving layer, Metabase, TMDL semantic model | Not started |
| 12 | Docker Compose: full stack runs with one command | Not started |
| 13 | End-to-end test (intake → determination → audit → warehouse → mart) + wrap-up | Not started |

## Phase 1b — Hardening

| # | Task | Status |
|---|---|---|
| 1 | Keycloak — citizen + worker realms | Not started |
| 2 | Row-level authorization — caseload scoping, sensitive-case flagging, `mart_access_review` | Not started |
| 3 | Mock external verification interface, with FTI-style safeguards applied | Not started |
| 4 | Airflow orchestration | Not started |
| 5 | Full medallion coverage of design §3.4.2's tables | Not started |
| 6 | Reporting widened — processing time vs. SNAP 30-day / 7-day standards | Not started |
| 7 | Governance completed — tokenization, column classification, `compliance-mapping.md` | Not started |
| 8 | Accessibility (Section 508/WCAG) | Not started |
| 9 | Observability (OpenTelemetry across API + pipeline) | Not started |
| 10 | Reference Terraform for Azure (not deployed) | Not started |

## Phases 2–5

Not started. Scope is defined in
`docs/design/2026-08-21-full-system-and-phased-roadmap.md` §5; task-level
breakdowns get written when each phase begins.

| Phase | Focus | Status |
|---|---|---|
| 2 | Policy Intelligence & Analytics AI — public hosted demo goes live here | Not started |
| 3 | Case Intake & Communication AI | Not started |
| 4 | Compliance & Integrity AI | Not started |
| 5 | Domain expansion (Medicaid/TANF) & real cloud deployment demos | Not started |

---

## Decisions already made (don't relitigate)

Recorded here so a fresh session doesn't reopen settled questions. Full
reasoning lives in the design docs.

| Decision | Choice | Where |
|---|---|---|
| DMN runtime | Drools/KIE, not Camunda | Roadmap §3.3 |
| Reporting | TMDL model-as-code + Power BI Service + Metabase container | Roadmap §3.3 |
| Audit log | Hash-chained, CI-verified | Roadmap §3.6 |
| Phase 1 shape | Split 1a / 1b | Roadmap §5 |
| Unit of eligibility | `PROGRAM_REQUEST`, not `APPLICATION` | Roadmap §3.4.1 |
| Determinations | Append-only; a change produces a new one | Roadmap §3.4.1 |
| Policy parameters | Effective-dated and immutable once published | Roadmap §3.5 |
| AI scope | All nine components stay in committed scope | Roadmap §5 |
| Cloud target | Azure Government by design; commercial Azure for any live demo | Roadmap §3.7 |
| Repo visibility | Private until Phase 1a ships | — |
| Java build tool | Maven (not Gradle) — dominant in the enterprise/government Java shops this repo targets; committed `./mvnw` wrapper is what CI runs | Phase 1a plan, "Versions pinned" |
| Python version | 3.12 via `uv`, not the system 3.14 — dbt-core support lags new releases | Phase 1a plan, "Versions pinned" |
| Bronze storage, Phase 1a | Local filesystem Delta tables; MinIO/S3 is a `storage_options` swap in Phase 1b | Phase 1a plan, Task 10 |
| Async messaging | **pgmq** (Postgres extension), not RabbitMQ/Kafka — document-intake jobs, correspondence dispatch, fraud-triage triggers. Portfolio-documented substitute, not an oversight. | Roadmap §3.3; tech-stack doc's Messaging tier + §4.11 |
| Ingestion pattern | Batch extract (Python job) for Phase 1a; CDC/Debezium documented as the production equivalent, not built — same treatment as pgmq, and for the same reason (needs a broker). | Roadmap §3.3; tech-stack doc's Data tier + §4.12 |

## Open questions

| Question | Blocking? | Notes |
|---|---|---|
| Does the current free Databricks tier permit the Phase 5 demo? | No — Phase 5 | Community Edition was replaced; verify before the README promises it |
| Fabric's current Government-cloud availability | No — Phase 5 | Narrower than Synapse's; verify before stating specifics |
