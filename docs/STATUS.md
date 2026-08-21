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

**Next action:** Task 3 — effective-dated `policy_parameter_set` and the
as-of SNAP parameter resolver.

---

## Verification log

Every row records a full-suite run, not a partial one.

| Date | Scope | Result |
|---|---|---|
| 2026-08-21 | Task 1 — `make test`, `make lint` (Java `./mvnw verify`, web `npm test`/`npm run typecheck`, Python `uv run pytest`/`ruff`/`mypy --strict`) | All green. Java: 1 test (context loads). Web: 1 test (app shell renders). Python: 2 tests (Settings config). No integration/e2e tests yet — no database, no Compose stack exists until Task 2 onward. |
| 2026-08-21 | Task 2 — `make test`, `make lint` (portal now runs 9 Testcontainers tests against a real Postgres 16 instance) | All green. Java: 9 tests — schema migration (V1/V2 apply, every Phase 1a table exists, every effective-dated table carries both date columns, household carries a mailing address), effective-dating/benefit-month constraint enforcement, and as-of query correctness for income_record. Web/Python unchanged from Task 1. Domain scope grew mid-task: `household` gained a mailing address (address_line1/2, city, state, zip_code) after clarifying that `household` is IES's case record — one HOH, many members via household_member, one or more applications over the case's life (including renewals) — and a case needs an address, which nothing in the schema carried yet. |

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
| 3 | `policy_parameter_set` — effective-dated SNAP parameters + as-of resolver | Not started |
| 4 | DMN decision tables on Drools/KIE, table-driven scenarios | Not started |
| 5 | Determination service — persisted determination + DMN trace | Not started |
| 6 | Hash-chained audit log + CI chain-verification job | Not started |
| 7 | Portal API — intake + worker case view (roles hardcoded) | Not started |
| 8 | React UI — intake form, case list, trace panel | Not started |
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

## Open questions

| Question | Blocking? | Notes |
|---|---|---|
| Does the current free Databricks tier permit the Phase 5 demo? | No — Phase 5 | Community Edition was replaced; verify before the README promises it |
| Fabric's current Government-cloud availability | No — Phase 5 | Narrower than Synapse's; verify before stating specifics |
