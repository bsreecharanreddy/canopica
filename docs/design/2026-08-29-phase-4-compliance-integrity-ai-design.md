# Canopica — Phase 4 Compliance & Integrity AI: Design Decisions

## 1. Scope recap

Phase 4, per the roadmap doc (§ Phase 4 — Compliance & Integrity AI): Fraud
Risk Triage, a fairness-audit report extension, a Case SLA/Compliance
Monitor, a QC / Payment Error Rate Assistant, a Caseworker SOP Copilot,
SOP Process-Improvement Mining, and data-quality anomaly detection with
AI-drafted root-cause summaries. Same governing principle as every phase
before it: AI drafts, flags, and explains; deterministic systems and human
reviewers own every binding decision. This is the most sensitive tier in
the roadmap by its own description — the README calls the fraud-triage
design "the strongest single artifact for evaluating AI judgment" — so
this doc is deliberately explicit everywhere a design choice touches
auto-adjudication risk.

Unlike Phase 3, this phase is **not** greenfield. Confirmed against the
actual repo state before writing this doc: four of the five gold marts
this phase needs already exist from Phase 1b —
`mart_processing_timeliness` (real, complete), `mart_determination_
outcomes`, `mart_worker_caseload`, and `mart_access_review` (all real).
`mart_payment_accuracy` exists but is an explicit placeholder — real
columns (`paid_amount`, `reviewed`, `payment_error_amount`), but its own
comment states the actual re-derivation logic is deferred to this phase.
Only `mart_fairness_audit` is genuinely new, and STATUS.md already
records why it was held back rather than built early: "built alongside
fraud-triage so it has both comparison axes from day one." So this phase
is mostly: finish one placeholder, build one new mart, and layer five AI
capabilities plus one new anomaly-scoring model on top of a data
foundation that already exists — not a data platform built from scratch
the way Phase 3's async infrastructure was.

Checked against current (2026) industry practice for anomaly-based fraud
triage, AI-assisted SLA/queue prioritization, LLM SOP-guidance patterns,
disparate-impact/proxy-feature fairness auditing, and dbt-native data
observability before finalizing — findings noted inline where they apply
(§2.2's anomaly-scoring method, §2.7's Elementary adoption) rather than
folded in as if they were the original brainstorm's own conclusions.

## 2. Decisions

### 2.1 `mart_fairness_audit` and the fairness CI gate

Already decided at the mechanism level (roadmap §3.3, restated in
STATUS.md's decisions table): **disparate-impact ratio across ACS-PUMS
demographic slices**, computed once and shared between a CI gate (blocks
a regression, same discipline as every other gate in this repo) and a
Power BI report page. Phase 2 already built this mechanism for the rules
engine; this phase's actual work is extending the *same* computation to
a second model (§2.2's fraud-risk score) rather than inventing a second
fairness methodology; a fraud-triage model that can't reuse a fairness
methodology already proven fit for a real eligibility decision would be
a worse-audited model than the one it flags, which defeats the point.

`mart_fairness_audit`'s grain: one row per (model, demographic slice,
outcome axis) — two models (`rules_engine`, `fraud_triage`) sharing one
table and one CI gate query, not two independent fairness systems. Built
from the ACS-PUMS-driven synthetic applicant generator's own demographic
fields (already exists, per the roadmap's synthetic-data-methodology doc)
joined against `fct_eligibility_determination` for the rules-engine axis
and the new `fraud_risk_score` table (§2.2) for the fraud axis.

### 2.2 Fraud Risk Triage

**Trigger**: a `pgmq` job (`fraud_scoring`, a third queue alongside
Phase 3's `document_intake`/`correspondence_dispatch`) enqueued in the
same transaction as an `eligibility_determination` commit — identical
timing and reliability shape to Phase 3's correspondence trigger (§2.4 of
that doc), kept off the binding transaction path per the roadmap's own
explicit instruction. The existing `worker/` process gets a third
consumer; no second worker deployable.

**Scoring approach, a real finding from the research pass**: no real
fraud-labeled data exists in this project — every applicant is synthetic,
and there is no ground truth for "this case was actually fraudulent" to
train a supervised classifier against. Supervised classification is
therefore off the table on a data-availability basis, not a preference.
**Unsupervised anomaly scoring** (isolation forest over a small,
engineered feature set — income volatility across resubmissions, rate of
verification-response discrepancies, household-composition change
frequency, benefit-amount percentile within household-size cohort) is
the right shape instead: it needs no labels, it's the standard current
pattern for exactly this class of problem (2026 industry practice
confirmed via research — anomaly-first scoring with a human decision
layer, not model-driven auto-adjudication), and its output is a bounded,
explainable number plus feature contributions rather than free-text
reasoning about *why* someone might be committing fraud — which would be
close to indefensible under audit even if it were accurate. Library:
scikit-learn (`IsolationForest`), self-hosted, $0, consistent with every
other tooling choice in this repo; runs inside a new `ai/fraud-triage/`
Python module, invoked by the worker as a library call — same
orchestrator-calls-library split Phase 3 already established between
`worker/` and `ai/`.

**Explicitly excluded features**: race, ethnicity, national origin, and
their documented statistical proxies (zip code as a standalone feature,
surname-derived signals, primary language) — confirmed against current
disparate-impact research: a model can produce discriminatory outcomes
from facially neutral features that reconstruct a protected attribute,
so "we don't use race" isn't sufficient on its own without also auditing
for proxy leakage. This is exactly what §2.1's fairness gate exists to
catch empirically, not just what the feature-exclusion list claims by
policy — both are needed together.

**No auto-adjudication, applied literally**: a score above threshold
writes a `fraud_risk_score` row (score, top contributing features, model
version, scored at) and makes the case visible in a review queue. Nothing
about the determination itself changes, no payment is held, no notice is
altered — the roadmap's own "surfaces cases to a human investigator's
queue only, never auto-adjudicates" is the literal behavior, not a
description of intent.

**Review queue access — a real fork, decided here**: the roadmap says
"investigator," but no such role exists in this system (`CUSTOMER`,
`WORKER`, `SUPERVISOR`, `ADMIN` are the whole set, confirmed against
`SecurityConfig.java`). Adding a new Keycloak role/realm-role mapping for
a single queue is real plumbing for a persona this project has no other
use for. **Decision: reuse `SUPERVISOR`** — already the role that "can
view any case" (Phase 1b design doc §2.1), which is exactly the scope a
fraud-review queue needs (cases outside the reviewer's own caseload), and
narrowest-existing-role-wins is this project's own stated posture
(`SecurityConfig.java`'s comment on the `ADMIN`-only parameter-publish
endpoint). QC review (§2.3) reuses `SUPERVISOR` for the same reason.

### 2.3 QC / Payment Error Rate Assistant

**Re-derivation mechanism**: re-run the *original* DMN determination
as-of its own `policy_parameter_set` version — this project's existing
reproducibility guarantee (roadmap §3.5) does the actual work here for
free. Concretely: a new internal re-evaluation path in `api/` (DMN
evaluation already lives there; this is not new Java infrastructure, just
a new caller of the existing evaluation service, called with the
determination's *stored* `as_of_date`/parameter-set id rather than
today's) produces a fresh `benefit_amount`, diffed against what
`eligibility_determination.benefit_amount` (and `mart_payment_accuracy.
paid_amount`) actually recorded. A non-zero diff populates the
placeholder's real columns: `reviewed = true`, `payment_error_amount` =
the diff.

**Sampling, not exhaustive re-derivation — grounded in the real SNAP QC
process this component is modeled on**: the federal SNAP Quality Control
process re-reviews a statistically valid *sample* of cases each cycle,
not every case ever decided. Re-deriving every historical determination
on every pipeline run is unbounded compute for no accuracy gain this
project's data volume doesn't already need — a sampled batch job
(triggered by Airflow, matching every other scheduled job in this
platform) is both the more realistic and the cheaper choice, and it's a
choice with a real domain citation behind it rather than an arbitrary
cost-cutting shortcut.

**AI's role**: strictly a plain-language discrepancy summary for the QC
reviewer ("this case's income was recalculated using the FY2026
parameter set instead of FY2025, producing a $34/month difference") —
composed from the diff and the two determinations' own trace records,
never from the LLM's own arithmetic. Same "AI explains numbers that are
already correct" boundary as Phase 2's Policy Q&A and Phase 3's
correspondence drafting. A QC reviewer (`SUPERVISOR`) confirms or
dismisses the flagged discrepancy; nothing auto-corrects a benefit
amount.

### 2.4 Case SLA/Compliance Monitor

**Deterministic layer — mostly already built.** `mart_processing_
timeliness` already computes SNAP's real 30-day/7-day-expedited standard
against *decided* cases. It cannot surface currently-pending, at-risk
cases, because a row only exists once a determination has been made. The
"at-risk worker queue" the roadmap asks for needs a live view of
`program_request` rows still in `SUBMITTED`/`PENDING_VERIFICATION`
status, aged against the same 7/30-day standard from `requested_on` —
kept as an **operational-database query in `api/`** (a new read endpoint),
not a dbt mart, because SLA risk needs to be current within the workday,
not as of last night's pipeline run. This mirrors the existing operational-
vs-warehouse split already present everywhere else in this system (case
detail is operational; historical reporting is warehouse).

**AI's role**: prioritization and summarization only, over that
deterministic list — never the deadline computation itself, which stays
a plain date comparison. A supervisor-facing queue ranks at-risk cases
(days remaining, ascending) and an LLM drafts a one-line reason a case is
stalled, grounded in that case's own audit trail and outstanding
`verification` rows (e.g. "awaiting INCOME verification, due in 2 days,
last worker action 6 days ago") — composed from real fields, not
free invention. `SUPERVISOR` role, same as §2.2/§2.3.

### 2.5 Caseworker SOP Copilot

**Pattern**: retrieve→generate, identical shape to Phase 2's Policy Q&A
— the same bounded-pipeline architecture already decided project-wide
(§2.9 below), not a new pattern for this component.

**Corpus — a real fork, decided here**: unlike Policy Q&A's real, public
7 CFR text, no public SOP corpus exists for this project to ground
against. **Decision: author a small, realistic SOP corpus specific to
Canopica's own SNAP process** (new application / reported change /
renewal — the three case types the roadmap names), written as markdown
procedure documents under `ai/sop_copilot/corpus/`, the same
authored-but-realistic posture the synthetic applicant generator already
takes with case data — fictional content standing in for what a real
agency's SOP manual would contain, stated as such rather than presented
as if sourced from a real document. Indexed into a **separate OpenSearch
index** from the policy corpus (not merged) — different trust/content
domain, same reasoning Phase 2's design doc already gives for keeping
retrieval provenance domain-scoped. Same hybrid (BM25 + k-NN, RRF fusion,
cross-encoder rerank) retrieval pipeline Policy Q&A already uses — no new
retrieval mechanism.

**Grounding/abstention**: same as Policy Q&A — insufficient corpus match
abstains rather than improvises a procedure. A wrong SOP answer is a
caseworker doing the wrong next step on a real case, which is exactly the
failure mode abstention exists to prevent.

### 2.6 SOP Process-Improvement Mining

**Pattern**: NL→tool-call→execute→summarize, extending the *existing*
Analytics Copilot mechanism (MetricFlow exposed over MCP, roadmap §3.3,
already decided) with new metrics — time-to-resolution by case type,
rejection-reason frequency (from `mart_determination_outcomes`), and
notice-rejection rate (from `notice.status`) — rather than a new
architecture. The LLM's job is synthesizing a narrative suggestion from
metrics it queried through the same authorization-gated tool-calling path
the Analytics Copilot already enforces (roadmap decisions table: "resolved
at tool-exposure time, before query compilation").

**Scope boundary, stated explicitly**: this component has no write path
of any kind. Canopica has no SOP-document CRUD to "change" — an SOP
change is a real-world process action entirely outside this system.
Mining produces an advisory narrative for a human process owner to act
on outside the app, the same way the fairness report is advisory
reporting, not an enforcement mechanism.

### 2.7 Data-quality anomaly detection + AI root-cause summaries

**Adopt Elementary**, not a hand-rolled anomaly detector. The tech-stack
tradeoffs doc already names Elementary (open-source, dbt-native, reads
dbt's own artifacts, layers anomaly detection/schema-change alerts/a
lineage-aware incident view on top) as this project's stated production-
equivalent gap — "genuinely not built in this repo" — for exactly this
roadmap item. Adopting it directly rather than building bespoke
statistical anomaly detection is the same "use the maintained thing"
posture this project already takes everywhere else (Postgres image
choice, pgmq, MinIO). Self-hosted, $0.

**AI's role**: when a dbt test fails *or* an Elementary anomaly fires,
gather structured failure context (model name, test name, a failing-row
sample, the metric's own historical baseline Elementary already tracks)
and draft a plain-language root-cause summary — same bounded pipeline as
everywhere else in this phase, human reads and investigates, nothing
auto-remediates a pipeline failure.

**Surfacing mechanism — a real fork, decided here**: this stack has no
chat-ops tool (no Slack integration exists or is planned), so "posted to
a Slack thread" (the pattern the research pass found as 2026's common
shape) doesn't fit without adding an integration this project has no
other reason to carry. **Decision: a new `data_quality_incident` table**
(data-platform-owned, serving layer) captures the summary, surfaced as a
small Metabase/Power BI page — same "a gate proves it's enforced, a
report proves it's visible" pattern §2.1's fairness gate already
establishes, reusing this project's existing reporting story instead of
inventing a notification channel.

### 2.8 Domain model additions

- **`fraud_risk_score`** (Java-owned, public schema): `id`,
  `program_request_id`, `determination_id`, `score`, `top_contributing_
  features` (jsonb), `model_version`, `scored_at`, `reviewed_by`,
  `reviewed_at`, `review_outcome` (`CONFIRMED_RISK`/`CLEARED`/null while
  pending). Written by the worker's fraud-scoring consumer via raw SQL,
  same pattern Phase 3's `DOCUMENT_CLASSIFIED`/`NOTICE_DRAFTED` events
  already use for Python-worker-authored rows.
- **`data_quality_incident`** (data-platform-owned, serving layer):
  `id`, `source` (`dbt_test`/`elementary`), `model_name`, `test_or_check_
  name`, `detected_at`, `summary` (the LLM-drafted root-cause text),
  `raw_context` (jsonb).
- **`mart_payment_accuracy`**: no schema change — its placeholder columns
  (`reviewed`, `payment_error_amount`) get real values once §2.3 lands;
  this is a logic change to how the mart is populated, not a new column.
- **New audit event types**, extending `AuditEventType` the same way V16
  and V18 already widened it twice: `FRAUD_FLAG_RAISED`, `FRAUD_FLAG_
  REVIEWED`, `QC_DISCREPANCY_FLAGGED`, `QC_REVIEW_COMPLETED`. SOP Copilot,
  SOP Mining, and the SLA monitor are read-only/advisory over existing
  data — no case-affecting write, so no new audit event type, the same
  reasoning Policy Q&A's own `ai.policy_qa_answer` needed no
  `AuditEventType` entry either.

### 2.9 Roles

No new Keycloak role. `SUPERVISOR` covers the fraud-review queue (§2.2)
and QC review (§2.3) — both are supervisor-tier oversight functions
already within that role's existing "view any case" scope. `ADMIN` is
unchanged (still narrowly scoped to parameter publishing). Stated here as
a decision rather than left implicit, since "investigator" and "QC
reviewer" read like distinct personas in the roadmap's prose and a future
session shouldn't reopen this by assuming a role that doesn't exist.

### 2.10 Observability

Extends the existing OTel/Jaeger/Prometheus/Grafana stack — no new tool,
same posture as Phase 2 §2.8 and Phase 3 §2.7. The worker's new
`fraud_scoring` consumer gets the same `traced_queue_cycle` span shape
Phase 3 Task 8 already built for the other two queues (`canopica.queue.
name`/`canopica.queue.message_age_seconds` attributes) — no new
instrumentation pattern, a third call site of an existing one. A new
Grafana panel: `fraud_risk_score` rows scored per day and the review
queue's own backlog depth, same "operational visibility into a queue,
not just its own SQL functions" reasoning as Phase 3's pgmq panel.

### 2.11 Stated defaults (not forks — recorded for completeness)

- **Isolation forest hyperparameters and score threshold**: tuned at
  implementation time against the synthetic data's own distribution, not
  hardcoded in this doc.
- **QC sample size/cadence**: a concrete percentage and schedule is a
  Task-level implementation detail, decided when that task is written,
  the same treatment Phase 3's doc gives pgmq retry-count tuning.
- **Elementary configuration** (which checks enabled, alert thresholds):
  implementation-time detail, not a phase-level fork.

### 2.12 Cross-cutting AI architecture & safety patterns

- **Bounded pipelines, not autonomous agents** — unchanged from Phase 2
  §2.10/Phase 3 §2.9. Every component in this phase is retrieve→generate
  (SOP Copilot), NL→tool-call→execute→summarize (SOP Mining), or a fixed
  score→flag→human-review pipeline (fraud, QC, SLA, data quality) — none
  gives an LLM a tool-call loop or the ability to act on its own output.
- **No auto-adjudication, anywhere in this phase** — the roadmap's own
  language for fraud triage ("never auto-adjudicates") is the literal
  behavior of every component here: a score, a flag, a summary, a
  ranked queue — never a changed benefit amount, a held payment, or a
  sent notice.
- **Fairness audit as a first-class output, not an afterthought** — the
  fraud-risk model is fairness-audited by the *same* CI-gated mechanism
  as the rules engine (§2.1), built specifically so both models have
  comparison axes from day one rather than the fraud model shipping
  first and a fairness check following later.
- **Structured output, not free text** — feature-contribution output,
  QC discrepancy diffs, and SOP retrieval results are all structured
  before an LLM ever composes a summary sentence over them, same standard
  as every other AI service in `ai/`.
- **Considered, deliberately deferred**: a supervised fraud classifier
  once/if real labeled outcome data exists (this project's synthetic data
  structurally can't support it now); a chat-ops (Slack) integration for
  data-quality alerts (§2.7's own fork — deferred as scope this project
  has no other reason to carry, not a missing feature); SOP mining
  writing directly to a corpus/document store (§2.6's own scope boundary
  — SOP change is a human/process action, not an app write path this
  system should ever gain).

## 3. Tradeoffs doc — refinements this unlocks

- The AI/Platform tier's existing **Fraud triage** row (present at the
  tier level, pre-dating this doc) gets the concrete mechanism: isolation-
  forest anomaly scoring over engineered features (not a supervised
  classifier — no labeled fraud data exists), scikit-learn, self-hosted.
- A new **Data quality observability** row: Elementary, dbt-native,
  self-hosted, $0 — closing the gap §5.7 (data observability) of that doc
  already names as unbuilt, now actually built rather than stated-but-
  absent.
- Note under §4 ("what this costs"): the QC Assistant re-derives a
  *sample* of determinations, not all of them (§2.3) — state explicitly
  that this means payment-error-rate reporting is a statistical estimate,
  same limitation the real federal SNAP QC process it's modeled on
  already carries, not a shortcut unique to this project.

## 4. What this doc does not settle

Exact isolation-forest hyperparameters/threshold, QC sample size and
cadence, Elementary's specific check configuration, and the SOP corpus's
exact document count/wording are Task-level implementation details,
decided when each task is actually written, not phase-level forks.

The implementation plan — file-by-file, task-by-task, mirroring
`docs/plans/2026-08-27-phase-3-implementation-plan.md`'s shape — is the
next step once this doc is reviewed and approved.

## 5. AI design pattern catalog (summary)

| Pattern | Where | Why chosen |
|---|---|---|
| Unsupervised anomaly scoring over supervised classification | §2.2 | No real fraud-labeled data exists — every applicant is synthetic. Isolation forest needs no labels and produces a bounded, explainable score rather than free-text reasoning about intent. |
| Explicit proxy-feature exclusion + empirical fairness audit together | §2.2/§2.1 | A feature-exclusion policy alone doesn't catch proxy leakage (e.g. zip code reconstructing a protected attribute) — the disparate-impact CI gate catches empirically what the exclusion list can only state as policy. |
| Reuse of the rules engine's own fairness mechanism for a second model | §2.1 | One disparate-impact-ratio computation, two models, one CI gate — a fraud model that can't clear the same bar as the eligibility decision it flags would be worse-audited than what it's checking. |
| Sampled, not exhaustive, re-derivation | §2.3 | Modeled directly on the real federal SNAP QC process, which samples rather than reviews every case — a real domain citation, not an arbitrary cost cut. |
| Operational (not warehouse) query for SLA at-risk cases | §2.4 | The deterministic deadline computation already exists in the warehouse for decided cases; at-risk *pending* cases need same-day currency a nightly pipeline can't give, so it stays a live API query. |
| Authored (not sourced) SOP corpus, stated as such | §2.5 | No public SOP corpus exists for this project to ground against, unlike Policy Q&A's real CFR text — same authored-but-realistic posture the synthetic applicant generator already takes, disclosed rather than implied to be real. |
| Extending the existing Analytics Copilot mechanism for SOP mining | §2.6 | NL→tool-call→execute→summarize over MetricFlow-via-MCP is already built and authorization-gated — a second instance of one mechanism, not a second architecture. |
| Adopting Elementary over a hand-rolled anomaly detector | §2.7 | Already named in the tradeoffs doc as this project's stated, unbuilt production-equivalent gap — "use the maintained thing," same posture as every other infra choice here. |
| No new role — reuse `SUPERVISOR` | §2.2/§2.3/§2.9 | Narrowest-existing-role-wins is this project's own stated posture; "investigator"/"QC reviewer" are oversight functions already within `SUPERVISOR`'s existing case-visibility scope. |
| No auto-adjudication anywhere in this phase | §2.12 | The roadmap's own language for the highest-scrutiny component in this repo, applied literally to every component in this phase, not just the one it was written about. |
