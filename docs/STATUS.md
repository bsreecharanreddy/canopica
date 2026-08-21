# Canopica — Implementation Status

**Read this file first.** It is the authoritative record of where the
implementation stands against the full plan. It is updated and committed
*in the same commit* as the work it describes, so it never drifts and
always survives a closed session, a new machine, or a fresh pair of eyes.

Last updated: **2026-08-21**

---

## Current position

**Design phase complete. Phase 1a not yet started.**

All three design docs are written, reviewed, and committed. The design has
been through one full review pass (2026-08-21) which added the domain
model, effective dating, and tamper-evident audit design, changed the DMN
runtime and reporting toolchain, and split Phase 1 into 1a/1b.

**Next action:** write the Phase 1a implementation plan (file-by-file),
then begin Task 1.

---

## Verification log

Nothing to verify yet — no implementation code exists. Once Phase 1a
starts, every row here records a full-suite run, not a partial one.

| Date | Scope | Result |
|---|---|---|
| — | — | No code yet |

---

## Phase 1a — Walking skeleton

The thinnest path that touches every layer and produces a real, correct,
auditable determination. Demoable on completion.

*Task list below is provisional and gets replaced by the implementation
plan's definitive breakdown once that's written.*

| # | Task | Status |
|---|---|---|
| 1 | Repo scaffolding, tooling, CI skeleton | Not started |
| 2 | Domain schema — operational entities per design §3.4.1, effective-dated | Not started |
| 3 | Synthetic applicant generator (ACS PUMS–driven) | Not started |
| 4 | `POLICY_PARAMETER_SET` — effective-dated SNAP thresholds and deductions | Not started |
| 5 | DMN decision tables on Drools/KIE, as-of-date aware | Not started |
| 6 | Determination service — writes `ELIGIBILITY_DETERMINATION` + `DETERMINATION_TRACE` | Not started |
| 7 | Hash-chained audit log + CI chain-verification job | Not started |
| 8 | Portal — intake form + worker case view (roles hardcoded) | Not started |
| 9 | Ingestion + one dbt path through bronze → silver → gold | Not started |
| 10 | Reporting — one report page + Metabase container | Not started |
| 11 | Docker Compose: full stack runs with one command | Not started |
| 12 | End-to-end test: intake → determination → audit → warehouse → mart | Not started |

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

## Open questions

| Question | Blocking? | Notes |
|---|---|---|
| Does the current free Databricks tier permit the Phase 5 demo? | No — Phase 5 | Community Edition was replaced; verify before the README promises it |
| Fabric's current Government-cloud availability | No — Phase 5 | Narrower than Synapse's; verify before stating specifics |
