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

At the coarsest level: **design phase complete, Phase 1a not started.**

## Phase plan

See the roadmap doc for full detail. At a glance:

- **Phase 1a — planned, not started.** Walking skeleton: intake →
  DMN determination (with persisted trace) → hash-chained audit → one dbt
  path through bronze/silver/gold → one report page. Roles hardcoded, no
  Keycloak, no Airflow, no OTel yet. Demoable on completion.
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

## `.claude/` tooling — deliberately not pre-built

No custom skills, agents, or hooks exist yet, on purpose. lore-native's
equivalent tooling (project skills, review agents, a stale-dev-server
hook) all encode specific incidents from that project's real history —
copying that structure here with invented content would mean fabricating
gotchas that never happened. Add them here the same way: when a real,
specific, repeatable lesson lands during implementation, write it down
then, not before.
