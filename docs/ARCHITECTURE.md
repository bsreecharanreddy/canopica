# Canopica — Architecture, in 5 Minutes

A short-form companion to the dated design docs in this directory, for a
reader who wants the shape of the system before deciding whether to spend
30 minutes in the full docs. If something here and a dated design doc ever
disagree, the dated doc wins — this page is a summary, not a source of
truth.

## The three tiers

**Core (deterministic, auditable).** Spring Boot API + a DMN decision-table
rules engine (Drools/KIE) + a hash-chained, append-only Postgres audit log.
Every binding decision — an eligibility amount, a denial reason — is made
here, never by the AI layer below. `UPDATE`/`DELETE` are revoked from the
application's database role at the schema level, not just by convention.

**Data (governed, reproducible).** A bronze/silver/gold dbt pipeline,
orchestrated by Airflow, with a semantic layer (dbt MetricFlow, published as
TMDL) sitting between the warehouse and every BI tool and AI capability that
reads from it — one metric definition, not one per dashboard. Proven
against real Databricks and Azure targets, not just a local DuckDB stand-in.

**AI (advisory, fenced off from every binding decision).** Nine LLM-backed
capabilities — policy Q&A, rule-authoring and dashboard-authoring copilots,
an analytics copilot, document classification, correspondence drafting,
fraud-risk triage, SLA/QC monitoring, a caseworker SOP copilot — all built
as fixed retrieve-then-generate pipelines, not an open-ended agent with
write access. None of them can write a binding decision; the ones closest
to money (fraud triage, QC) produce a flagged *review item* a human
disposes of, never a determination.

## The three hardest problems, and how they're actually solved

**1. A determination has to be reproducible years later, exactly.** Federal
program thresholds change annually; a household's facts change mid-month;
an appeal or an audit needs the *original* answer, not today's answer run
against today's numbers. Solved by making policy parameters effective-dated
and immutable once published, storing the exact parameter-set version each
determination used (never a pointer to "current"), and persisting the full
DMN evaluation trace. Verified by test, not asserted: an old determination
re-run against its own historical parameter version reproduces its original
dollar amount. Phase 4's QC re-derivation depends on this holding exactly —
its whole function is re-deriving what a case *should* have produced.

**2. "Immutable audit log" has to mean something a reader can check, not
just a table name.** A table with `UPDATE` granted to the app role isn't
immutable — anyone holding that grant can rewrite history. Each audit event
carries the hash of its predecessor plus its own payload, chaining every
row to the one before it; `UPDATE`/`DELETE` are revoked from the
application role at the database level, so the app can only append; and a
CI job walks the full chain on every run and fails the build if it doesn't
verify. A governance claim turned into a control that's actually
demonstrated, not just written down.

**3. Nine real LLM capabilities, and none of them may quietly become the
decision-maker.** The risk isn't a model refusing to help — it's a model
*confidently* doing the wrong thing and nobody noticing. The fixes are
boring on purpose: every generated citation is checked against the actual
retrieved source before it reaches a user (Policy Q&A); every field or
measure a copilot references is checked against the real schema before its
proposal is returned (rule-authoring, dashboard-authoring); an eval-suite
CI gate (RAGAS/DeepEval faithfulness, context precision/recall against a
golden question set) blocks a regression from merging; a fairness gate
checks disparate impact before a scoring model ships. A live-model bug
found during Phase 3 is the concrete version of the risk this guards
against: asked about a document with no relevant content, the model
confidently filled in a plausible-looking default value at high confidence
instead of abstaining — exactly the failure mode §2.3 of the Phase 3 design
doc names as never acceptable, closed by an explicit prompt rule and a
regression test against the real model, not just documented as a known
issue.

## The three biggest tradeoffs

**1. Self-hosted, local models — materially weaker than frontier models, by
design.** Ollama running locally is what makes this $0 to clone and run;
it is also measurably worse than a hosted frontier model. The eval suite's
absolute scores aren't meaningful as a claim about what this architecture
could achieve — they're meaningful as a relative baseline and as proof the
gate mechanism itself works and catches a regression. The public demo
swaps to a small hosted model specifically because a judge and a
publicly-reachable demo don't carry the same self-hosting rationale the
*generation* model under test does.

**2. One engineer, one environment, thousands of records — not millions.**
No dev/sit/uat/prod promotion pipeline, no separation of duties between
whoever writes the rules and whoever reviews them, no proof of index
design or query performance under real concurrency or real write volume.
The architecture (medallion layering, effective-dating, the audit chain,
the AI boundary) is what's being demonstrated; scale and organizational
controls are stated as out of scope rather than silently absent.

**3. The realistic production target for this data class is Azure
Government, and Azure Government is not what got deployed.** The data this
system models — income verification, later health data — is exactly the
category real state systems run in a sovereign cloud rather than
commercial Azure. Two corrections worth stating precisely, because they
cut in opposite directions from the usual assumption: IRS 1075 compliance
specifically is *not* the forcing function it's commonly believed to be
(Microsoft's own FAQ says so explicitly — both commercial and Gov Azure
hold the same FedRAMP High P-ATO); and Azure Container Apps, the service
this repo's Terraform actually targets, **does not exist in Azure
Government at all**, which would force a real deployment onto AKS or App
Service instead. Azure Government isn't self-service, so this project's
live demo runs on commercial Azure — documented as a stated substitution
with a specific, named consequence, not glossed over.

## Read next

- [`docs/design/2026-08-21-full-system-and-phased-roadmap.md`](design/2026-08-21-full-system-and-phased-roadmap.md) — the full architecture and phased roadmap
- [`docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`](design/2026-08-21-tech-stack-and-production-tradeoffs.md) — every stack choice mapped to its real production equivalent, and 20 numbered compromises stated explicitly (§4 is the source for the tradeoffs above)
- [`docs/STATUS.md`](STATUS.md) — live implementation status, task by task, with a verification log of what was actually run and what it found
