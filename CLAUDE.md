# Canopica (CLAUDE.md)

Read this before doing anything in this repo.

## What this project is

Canopica is a portfolio project: a rules-driven benefits-eligibility platform
(customer/worker portals, a DMN rules engine, a governed data pipeline,
Power BI reporting) with an AI capability layer built on top, targeting
senior data/full-stack/BI roles. It is an independent project inspired by
publicly documented patterns in how state health & human services
eligibility systems generally work — **never name a real agency, a real
state benefits program, or a consulting firm/systems integrator anywhere
in this repo's code, docs, or commit history; call the system only Canopica.**

To be unambiguous about the boundary: this rule is about not identifying
any real-world client, employer, or deployed system. Naming *technology
vendors and products* is fine and expected — Databricks, Power BI,
Keycloak, Azure, Drools and the rest appear throughout the docs by design.
Don't scrub those.

## Read this first

**`docs/STATUS.md` before anything else.** It is the authoritative record
of where implementation stands against the full plan — current position,
what was last verified green, what's next, and which decisions are already
settled and shouldn't be reopened. It is updated in the same commit as the
work it describes, so it is never stale. Start there, then come back here.

`docs/design/2026-08-21-full-system-and-phased-roadmap.md` is the
authoritative architecture and roadmap doc — read it before making any
structural decision. It carries the domain model (§3.4), the temporality
and determination-reproducibility design (§3.5), and the tamper-evident
audit design (§3.6), all of which constrain implementation.

`docs/design/2026-08-20-phase1-vertical-slice.md` is the earlier
Phase-1-only doc it expands on; kept as-is rather than overwritten, as a
record of how the design evolved. **It is superseded on four points** —
DMN runtime, reporting toolchain, audit-log design, and Phase 1's shape —
listed in a table at the top of the roadmap doc. When the two disagree,
the roadmap doc wins.

`docs/plans/` holds the per-phase implementation plans (file-by-file, task
by task, each task carrying its own tests and its own commit). The active
one is `docs/plans/2026-08-21-phase-1a-implementation-plan.md`. A plan is
written from the design docs and approved before any code for that phase
gets written; `docs/STATUS.md` tracks progress through it.

`docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md` maps every
stack choice to its real production equivalent and states what each
substitution costs. Read it before changing a stack choice, so a
compromise doesn't get "fixed" without knowing why it was made.

Don't duplicate their content here — this file is for orientation and
status, not architecture.

## The one governing principle

AI drafts, flags, explains, and assists. Deterministic systems (the DMN
rules engine, scheduled pipeline jobs) and human reviewers own every
binding decision, every scheduled operation, and every dollar amount. This
applies to every AI capability in the roadmap doc without exception —
if an implementation choice would put an LLM in charge of a binding
decision (eligibility amount, a fraud determination, an auto-sent notice),
that's a design bug, not an implementation detail to work around.

## Current status

`docs/STATUS.md` holds it, at task granularity. Deliberately not duplicated
here — two places to record the same thing means one of them is wrong.

At the coarsest level: **Phase 1a done, verified end-to-end. Phase 1b
in progress (9 of 10 tasks done — identity, row-level authorization, mock
external verification, orchestration, full medallion coverage, widened
reporting, governance, accessibility, and observability; only reference
Terraform for Azure remains).**

## Phase plan

See the roadmap doc for full detail. At a glance:

- **Phase 1a — done, verified end-to-end.** Walking skeleton: intake →
  DMN determination (with persisted trace) → hash-chained audit → one dbt
  path through bronze/silver/gold → one report page. Roles hardcoded, no
  Keycloak, no Airflow, no OTel yet — see the "Deferred out of Phase 1a, on
  purpose" list at the bottom of the Phase 1a plan for the full,
  intentional scope boundary. Verified for real, not just by test count:
  `data-platform/tests/test_end_to_end.py` (`pytest -m e2e`, CI's `e2e`
  job) submits an application through the real portal API, runs a real
  determination as a worker, reads its persisted DMN trace, verifies the
  real hash-chained audit log, rebuilds the real dbt warehouse from the
  live operational database, and confirms the gold mart's dollar amount is
  the exact number the rules engine decided — the same slice is also
  walkable by hand via `docs/demo.md`, which was itself run once for real
  (not just written from the code) before being committed. Demoable, and
  demoed.
- **Phase 1b — planned.** Hardening: Keycloak, caseload-scoped row-level
  authorization, mock external verification interface, Airflow, full
  medallion coverage, governance mapping, accessibility, observability.
- **Phase 2 — planned.** Policy Intelligence & Analytics AI.
- **Phase 3 — planned.** Case Intake & Communication AI.
- **Phase 4 — planned.** Compliance & Integrity AI (fraud triage, SLA/QC,
  SOP copilot).
- **Phase 5 — planned.** Domain expansion (Medicaid/TANF) & real cloud
  deployment demos.

## Testing policy — non-negotiable

**No implementation code gets committed without tests, and the full suite
runs before every push.** Not the tests for the area that changed — the
whole suite, every time. The point is catching regressions in work built
in earlier phases, which is exactly what a growing multi-phase project
breaks silently.

Per layer:

| Layer | Tooling | What must be covered |
|---|---|---|
| Rules engine | JUnit 5, table-driven | One test per SNAP scenario: gross-income test, each deduction applied in the correct order, net-income test, categorical eligibility override, and **as-of-date correctness** — an old determination re-run against its own parameter version still produces its original answer |
| Determination + audit | JUnit 5 + Testcontainers (real Postgres) | Trace is persisted and complete; audit chain verifies; `UPDATE`/`DELETE` on the audit table are actually refused |
| Portal API | Spring Boot Test | Endpoint contracts, authorization (including row-scoping once Phase 1b lands) |
| Portal UI | Vitest + React Testing Library | Component behavior, plus accessibility assertions once Phase 1b lands |
| Python services | `pytest`, `ruff`, `mypy --strict` | Unit + integration; the synthetic generator's distributions; every AI service's I/O contract |
| Data platform | dbt tests | `not_null` / `unique` / `relationships` / `accepted_values` on every model, plus custom tests asserting no unmasked PII-shaped column reaches gold |
| End to end | pytest | The full slice: intake → determination → audit → warehouse → mart |
| AI layer (Phase 2+) | Eval suite in CI | Groundedness and citation accuracy; fairness disparate-impact gate |

CI runs all of it on every push. A red suite blocks the merge. When
reporting a step as done, state the actual result — including which tests
failed, if any did.

## Language policy — Python-first where the choice is open

Python is the default for anything where the language is genuinely open:
the data platform, the synthetic generator, every AI service, the eval and
fairness harnesses, and tooling. Use current-generation tooling — `uv`,
Pydantic v2, `ruff`, `mypy --strict`, `pytest`, FastAPI, Polars where it
beats pandas — not older equivalents.

Java/Spring stays where it earns its place and is not to be rewritten
away: the portal API (deliberate full-stack Java signal for role
targeting) and the rules engine (Drools/KIE is JVM-only, and the DMN
evaluation lives inside the portal service). Everything else is Python.

## Conventions

- Single monorepo (see the roadmap doc's repo layout).
- Every design decision goes through brainstorm → dated doc in
  `docs/design/` → user approval → implementation plan, before any code
  gets written. Don't skip straight to code on a new subsystem.
- Every phase gets its own implementation plan before implementation
  starts, and a wrap-up/verification pass before being called done.
- **One commit per completed step**, not one bundled commit at phase end.
  Each step's commit carries its own code, its own tests, and its own
  green full-suite run.
- **`docs/STATUS.md` updates in the same commit as the work it
  describes** — never as a separate follow-up commit, or it drifts and
  stops being trustworthy.
- **The README's "Architecture, at a glance" Mermaid diagram updates in
  the same commit as any change to what it depicts** — a new/removed
  component, a renamed tier, a changed data flow. Same reasoning as the
  STATUS.md rule above: a diagram nobody keeps current is worse than no
  diagram, because it actively misleads a reader instead of just being
  silent.

## `.claude/` tooling — added only for real, already-settled things

Unlike lore-native's incident-driven tooling (a stale-dev-server hook, a
Maestro-gotcha skill — each one encoding a specific thing that actually
went wrong), Canopica has almost no implementation history yet, so its
`.claude/` tooling only codifies things that were *already true* before
any tooling existed: standing policies this file already states as
non-negotiable, and the one real incident hit so far. Nothing here is
anticipatory — no fabricated gotchas for problems this repo hasn't had.

- **`canopica-task-checkpoint` skill** — the per-task regression gate (full
  `make test`/`make lint`, STATUS.md same-commit, one-commit-per-task)
  the testing policy above already requires. Codifies the checklist, adds
  nothing new to it.
- **`canopica-design-decision` skill** — the brainstorm → dated doc → approval
  → implementation-plan workflow from the Conventions section below, plus
  exactly where a settled decision gets recorded (STATUS.md, roadmap
  doc, tradeoffs doc). First used for real recording the pgmq decision
  (commit 683747a) before this skill existed; the skill just makes that
  same shape repeatable without re-deriving it from prose each time.
- **`check-status-md-commit.sh` hook** (PreToolUse/Bash) — warns,
  non-blocking, if a `git commit` stages files outside `docs/` without
  `docs/STATUS.md`, enforcing the same-commit rule above mechanically
  instead of relying on memory.

The Ryuk/Testcontainers-Python incident (Task 6 — see STATUS.md's
verification log) is *not* duplicated here as a skill: it's already fully
codified at the right layer, `make test`'s `TESTCONTAINERS_RYUK_DISABLED`
and `data-platform/tests/conftest.py`'s docstring, and a Claude-specific
artifact on top would be redundant.

Add more here the same way lore-native does: when a real, specific,
repeatable lesson actually lands during implementation, write it down
then — not before.
