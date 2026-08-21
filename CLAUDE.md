# IES — Integrated Eligibility System (CLAUDE.md)

Read this before doing anything in this repo.

## What this project is

IES is a portfolio project: a rules-driven benefits-eligibility platform
(customer/worker portals, a DMN rules engine, a governed data pipeline,
Power BI reporting) with an AI capability layer built on top, targeting
senior data/full-stack/BI roles. It is an independent project inspired by
publicly documented patterns in how state health & human services
eligibility systems generally work — **never name a real agency, a real
state benefits program, or a consulting firm/systems integrator anywhere
in this repo's code, docs, or commit history; call the system only IES.**

To be unambiguous about the boundary: this rule is about not identifying
any real-world client, employer, or deployed system. Naming *technology
vendors and products* is fine and expected — Databricks, Power BI,
Keycloak, Azure, Drools and the rest appear throughout the docs by design.
Don't scrub those.

## Read this first

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

**Design phase — no implementation yet.** All three design docs above are
written, reviewed, and committed. The design has been through one full
review pass (2026-08-21) which added the domain/temporality/audit design,
switched the DMN runtime and reporting toolchain, and split Phase 1 into
1a/1b. Phase 1a has not been started. This section gets updated
phase-by-phase as work actually happens, the same way it would in any
long-running project.

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

## Conventions

- Single monorepo (see the roadmap doc's repo layout).
- Every design decision goes through brainstorm → dated doc in
  `docs/design/` → user approval → implementation plan, before any code
  gets written. Don't skip straight to code on a new subsystem.
- Every phase gets its own implementation plan before implementation
  starts, and a wrap-up/verification pass before being called done —
  process TBD in detail once Phase 1's plan is written, at which point
  it's worth capturing here.

## `.claude/` tooling — deliberately not pre-built

No custom skills, agents, or hooks exist yet, on purpose. lore-native's
equivalent tooling (project skills, review agents, a stale-dev-server
hook) all encode specific incidents from that project's real history —
copying that structure here with invented content would mean fabricating
gotchas that never happened. Add them here the same way: when a real,
specific, repeatable lesson lands during implementation, write it down
then, not before.
