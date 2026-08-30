# Phase 4 — Compliance & Integrity AI: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> Execute tasks in order, one commit per completed task, `docs/STATUS.md`
> updated in that same commit (CLAUDE.md, "Conventions"). Run the
> `canopica-task-checkpoint` skill's gate (`make test`, `make lint`, STATUS.md,
> one commit) after every task. Push at natural task-cluster boundaries
> (roughly every 2-4 tasks, or whenever a task's correctness genuinely
> depends on CI-only conditions this repo can't fully verify locally), not
> after every single commit and not held to the end of the phase — Actions
> minutes are a metered, finite resource this project has already hit real
> limits against.

**Goal:** Fraud Risk Triage, a fairness-audit mechanism shared across the
rules engine and the fraud model, a QC / Payment Error Rate Assistant, a
Case SLA/Compliance Monitor, a Caseworker SOP Copilot, SOP
Process-Improvement Mining, and data-quality anomaly detection — the last
tier of AI capability the roadmap commits to, and the most sensitive one:
no component in this phase ever changes a benefit amount, holds a
payment, or sends a notice. Every one produces a score, a flag, a ranked
queue, or a summary for a human to act on.

**Spec:** `docs/design/2026-08-21-full-system-and-phased-roadmap.md` §3.2/
§3.3/§3.4/§5 (what), `docs/design/2026-08-29-phase-4-compliance-integrity-
ai-design.md` (how — read this one first, it resolves every open question
this plan assumes as settled), `docs/design/2026-08-21-tech-stack-and-
production-tradeoffs.md` (fidelity/cost rationale for every substitution
below, including this plan's own additions to it).

**Starting point, worth internalizing before Task 1 — confirmed against
the actual repo state while writing this plan, correcting three
assumptions the design doc made from the roadmap's prose rather than the
code:**

1. **The QC Assistant's core re-derivation mechanism already exists.**
   `DeterminationService.reproduce(UUID determinationId)`
   (`api/.../determination/DeterminationService.java`) already re-evaluates
   a stored determination against its own recorded parameter-set version
   and returns the result without persisting anything — built in Phase 1a
   to satisfy the §3.5 reproducibility guarantee, proven by
   `DeterminationReproducibilityTest`, but never called from anywhere else
   in the codebase. Task 4 below is a caller and a diff, not new DMN
   infrastructure — smaller scope than the design doc's §2.3 implied.
2. **No fairness-audit mechanism exists yet, for either model.** The
   design doc's §2.1 describes this phase as "extending" a mechanism
   "Phase 2 already built... for the rules engine" — that mechanism was
   never built. `STATUS.md`'s own decisions table already records why:
   *"Deferred from Phase 1b to Phase 4, built alongside fraud-triage so it
   has both comparison axes from day one."* Confirmed by grep: no
   `disparate_impact`/`fairness_audit` code, table, or CI job exists
   anywhere in this repo today. Task 1 below builds the mechanism itself
   (for the rules-engine axis, which needs nothing this phase hasn't
   already got), not just an extension.
3. **No race/ethnicity demographic field exists anywhere in this project's
   data — a real gap in exactly the axis the fairness audit's own headline
   justification (the Dutch childcare-benefits algorithm) is about.**
   `SyntheticPerson` (`data-platform/.../synthetic/models.py`) samples
   `sex` and `relationship` only; `fetch_pums.py`'s ACS PUMS ingestion
   never reads PUMS's own `RAC1P`/`HISP` variables. A disparate-impact
   audit that can only slice by sex isn't the audit the design doc
   describes. Task 1 adds this field for real, sourced from actual ACS
   PUMS data the same authored-but-real posture the rest of the synthetic
   generator already takes — not fabricated, and not skipped.

None of this changes any decision in the design doc — the mechanism,
model, and architecture choices all stand. It changes this plan's actual
task boundaries versus what a plan written from the design doc's prose
alone would have assumed.

---

## Global constraints

Everything Phase 1a's, Phase 1b's, Phase 2's, and Phase 3's plans stated
still applies (never name a real agency; full suite before every push;
synthetic data only; AI never makes a binding decision; structured output
at every AI→system boundary; async enqueue calls share the triggering
write's own transaction). Phase 4 adds:

19. **No auto-adjudication, anywhere in this phase, generalized past
    Phase 3's document/correspondence-specific version of this rule
    (constraint 16).** Fraud triage writes a score and a queue entry; QC
    writes a discrepancy and a queue entry; the SLA monitor writes a
    ranked list and a one-line reason; data-quality anomalies write a
    summary. None of the four ever changes a benefit amount, holds a
    payment, alters a determination, or sends a notice. If a task's own
    design would let any pipeline in this phase take one of those actions
    without an explicit human decision in between, that is a design bug —
    stop and revise the task.
20. **The fraud-risk model's feature set excludes race, ethnicity,
    national origin, and their documented statistical proxies** (zip code
    as a standalone feature, surname-derived signals, primary language) —
    enforced in the feature-engineering code itself, not just stated in a
    doc, and checked empirically by Task 1/3's fairness gate rather than
    assumed sufficient on its own (design doc §2.2).
21. **The QC Assistant's discrepancy summary is composed only from the
    diff and the two determinations' own trace records** — never the
    LLM's own arithmetic. Same "AI explains numbers that are already
    correct" boundary Phase 2's Policy Q&A and Phase 3's correspondence
    drafting already hold to.
22. **SOP Process-Improvement Mining has no write path of any kind.**
    Canopica has no SOP-document store to write to and no metric-authoring
    endpoint this task should ever gain — it produces an advisory
    narrative only, over metrics queried through the existing
    authorization-gated Analytics Copilot tool-calling path, never a new
    one.
23. **Demographic fields added for fairness auditing (race/ethnicity) get
    the same PII-shaped handling as every other sensitive column** — silver
    layer classification/tokenization, and the fairness mart's own grain
    (one row per model/slice/outcome-axis, an aggregate) is the only place
    a demographic value is ever allowed to reach gold; no report row in
    this phase carries one person's individual demographic value.

### New dependencies this phase

| Component | Choice | Why |
|---|---|---|
| Anomaly scoring | `scikit-learn` (`IsolationForest`) | Design doc §2.2; tradeoffs doc's new Fraud risk triage row |
| Data-quality observability | Elementary (`elementary-data`, dbt package + CLI) | Design doc §2.7; tradeoffs doc's new Data quality observability row |
| Worker queues | Two more `pgmq` queues: `fraud_scoring` (third), `qc_summary` (fourth) | Design doc §2.2; extends Phase 3's two-queue worker with the same read/dispatch loop, no new mechanism |

### Prerequisites before Task 1

- [ ] Confirm the exact ACS PUMS person-level file still exposes `RAC1P`
      and `HISP` under those names against the Census Bureau's current
      PUMS data dictionary before writing `fetch_pums.py`'s parsing code —
      `fetch_pums.py` already pins a specific PUMS vintage; verify against
      that same vintage, not assumed from general PUMS knowledge.
- [ ] Confirm `scikit-learn`'s current stable version and pin it in
      `ai/pyproject.toml` at implementation time, not assumed here.
- [ ] Confirm Elementary's current stable version and its actual
      compatibility with this project's pinned `dbt-core`/`dbt-duckdb`
      versions before adding it to `data-platform/pyproject.toml` — a
      version mismatch here is a real, checkable risk, not a formality.

---

## File structure (additions only)

```
canopica/
  data-platform/
    src/canopica_data/synthetic/
      models.py                               <- Task 1 done (+race, +hispanic_origin on SyntheticPerson)
      fetch_pums.py                            <- Task 1 done (+RAC1P/HISP marginals, re-run live)
      generator.py                             <- Task 1 done (samples race/hispanic_origin)
      data/acs_pums_marginals.json             <- Task 1 done (regenerated from real Census data)
    src/canopica_data/serving/materialize.py    <- Task 1 done (+mart_fairness_audit to GOLD_MARTS)
    dbt/canopica_warehouse/models/
      silver/dim_person.sql                    <- Task 1 done (+race, +hispanic_origin, silver tier)
      silver/fct_household_member.sql          <- Task 1 done (new; household_key <-> person_key bridge)
      silver/fct_fraud_risk_score.sql          <- Task 3 done (new; latest-by-_ingested_at dedup)
      silver/silver.yml                        <- Task 1 done (+fct_household_member, +race/hispanic_origin
                                                   cols, +fix to fct_audit_event's stale accepted_values)
                                                <- Task 3 done (+fct_fraud_risk_score entry)
      gold/mart_fairness_audit.sql             <- Task 1 done (rules-engine axis only)
                                                <- Task 3 done (+fraud-triage axis)
      gold/mart_payment_accuracy.sql           <- Task 4 done (modified: real reviewed/payment_error_amount)
      gold/gold.yml                            <- Task 1 done (+mart_fairness_audit entry)
      semantic/semantic_models.yml             <- Task 1 done (+sem_fairness_audit)
    dbt/canopica_warehouse/tests/
      gate_no_disparate_impact.sql             <- Task 1 done (the actual CI gate, a dbt singular test)
    dbt/canopica_warehouse/models/silver/
      fct_payment_error_review.sql             <- Task 4 done (new; real silver-layer naming, not the
                                                   plan's original staging/stg_ guess -- see Task 4's
                                                   own file-list note for why)
    tests/
      test_generator.py                        <- Task 1 done (+race/hispanic_origin distribution test)
      test_fairness_gate.py                    <- Task 1 done (proves the gate fires + withholds)
      test_materialize.py                      <- Task 1 done (+mart_fairness_audit row-count assertion)
      conftest.py                              <- Task 1 done (+seeded_fairness_dsn fixture)
  api/src/main/resources/db/migration/
    V22__person_demographics.sql               <- Task 1 (done: race/hispanic_origin on person)
    V23__fraud_risk_score.sql                  <- Task 2 done
    V24__audit_event_type_fraud_flag_raised.sql <- Task 2 done (widen CHECK for FRAUD_FLAG_RAISED
                                                   only -- see Task 2's own file-list note for why
                                                   this renumbers away from the plan's original
                                                   single "widen all four at once" V25)
    V25__audit_event_type_fraud_flag_reviewed.sql <- Task 3 done (widen CHECK for FRAUD_FLAG_REVIEWED
                                                   only)
    V26__payment_error_review.sql,
    V27__audit_event_type_qc_discrepancy_flagged.sql <- Task 4 done (real next numbers when it
                                                   landed, not V25 as the plan originally guessed --
                                                   see Task 4's own file-list note)
  api/src/main/java/canopica/api/
    fraud/FraudRiskScore.java, FraudRiskScoreRepository.java           <- Task 2 done
    api/FraudReviewController.java             <- Task 3 done (review queue, confirm/clear)
    fraud/FraudReviewService.java              <- Task 3 done (the one Java write to fraud_risk_score)
    qc/PaymentErrorReview.java, PaymentErrorReviewRepository.java, QcSamplingService.java  <- Task 4 done
    api/QcController.java                      <- Task 4 done (internal sample-trigger endpoint only;
                                                   Task 5 adds the review queue/confirm/dismiss endpoints
                                                   to the same file)
    caseload/AtRiskCaseQuery.java (or similar, in an existing package)  <- Task 6
    api/SlaMonitorController.java               <- Task 6
    audit/AuditEventType.java                   <- Task 2/3/4 done (modified: +FRAUD_FLAG_RAISED,
                                                   +FRAUD_FLAG_REVIEWED, +QC_DISCREPANCY_FLAGGED -- see
                                                   Task 2's own file-list note on why this isn't +4 at
                                                   once as originally planned)
  ai/src/canopica_ai/
    fraud_triage/
      features.py                              <- Task 2 done (feature engineering, proxy-exclusion enforced here)
      score.py                                 <- Task 2 done (IsolationForest wrapper)
      service.py                                <- Task 2 done
    qc_assistant/
      draft.py, validate.py, service.py         <- Task 4 done (draft/validate/service split, not the
                                                   plan's original summarize.py+service.py -- see Task 4's
                                                   own file-list note)
    sla_monitor/
      prioritize.py, summarize.py, service.py    <- Task 6
    sop_copilot/
      corpus/*.md                               <- Task 7 (authored SOP documents)
      corpus/index.py                           <- Task 7 (mirrors policy_intelligence/corpus/index.py)
      retrieval.py, service.py, api.py           <- Task 7
    analytics_copilot/
      metric_catalog.py                         <- Task 8 (modified: +new metrics)
      sop_mining_prompts.py or similar           <- Task 8
    data_quality/
      elementary_ingest.py                      <- Task 9 (reads Elementary's own result artifacts)
      root_cause.py                             <- Task 9
      service.py                                <- Task 9
  ai/tests/
    test_fraud_triage.py                        <- Task 2 done
    test_qc_assistant.py                        <- Task 4 done
    test_sla_monitor.py                          <- Task 6
    test_sop_copilot.py                          <- Task 7
    test_data_quality.py                         <- Task 9
  worker/src/canopica_worker/
    fraud_scoring_consumer.py                    <- Task 2 done
    qc_summary_consumer.py                       <- Task 4 done
    main.py                                      <- Task 2/4 done (modified: +fraud_scoring handler,
                                                   +qc_summary handler), config.py (modified: +2 queue names)
  worker/tests/
    test_fraud_scoring_consumer.py               <- Task 2 done
    test_qc_summary_consumer.py                  <- Task 4 done
  ui/src/pages/
    FraudReviewPage.tsx                          <- Task 3 done
    QcReviewPage.tsx                              <- Task 5
    SlaMonitorPage.tsx                            <- Task 6
    SopCopilotPage.tsx                            <- Task 7
  infra/airflow/dags/
    canopica_pipeline_dag.py                      <- Task 4 done (modified: +run_qc_sample task), Task 6 (modified: +SLA-summary-refresh task), Task 9 (modified: +Elementary run)
  data-platform/dbt/canopica_warehouse/
    packages.yml                                  <- Task 9 (modified: +elementary-data)
  api/src/main/resources/db/migration/
    (data_quality_incident is data-platform/serving-layer-owned, not an
    api/ migration — see Task 9)
  data-platform/src/canopica_data/serving/
    materialize.py                                <- Task 9 (modified: +data_quality_incident table)
  .github/workflows/ci.yml                        <- modified: fairness-gate step in the dbt/data-platform job (Task 1), Elementary run in the same job (Task 9)
  Makefile                                         <- modified as needed per task
```

---

## Task list

| # | Task | Deliverable |
|---|---|---|
| 1 | Demographic fields + fairness-audit mechanism | Real race/ethnicity data from ACS PUMS; `mart_fairness_audit` and its CI gate, rules-engine axis only |
| 2 | Fraud Risk Triage: scoring | `fraud_risk_score` table; `ai/fraud_triage/` isolation-forest module; `fraud_scoring` queue + worker consumer |
| 3 | Fraud Risk Triage: review + fairness extension | `SUPERVISOR`-scoped review queue/UI; `mart_fairness_audit` extended to the fraud-triage axis |
| 4 | QC / Payment Error Rate Assistant: sampling | `payment_error_review` table; sampled `reproduce()`-based re-derivation via Airflow; AI discrepancy summary; `mart_payment_accuracy` populated for real |
| 5 | QC review UI | `SUPERVISOR` confirms/dismisses a flagged discrepancy |
| 6 | Case SLA/Compliance Monitor | Live at-risk-case query; AI prioritization + one-line stall reason; supervisor UI |
| 7 | Caseworker SOP Copilot | Authored SOP corpus, separate OpenSearch index, retrieve→generate service + UI |
| 8 | SOP Process-Improvement Mining | New Analytics Copilot metrics; narrative-synthesis extension, no new architecture |
| 9 | Data-quality anomaly detection | Elementary adopted; `data_quality_incident` table; AI root-cause summaries; reporting page |
| 10 | Observability & Phase 4 wrap-up | `gen_ai.*`/queue spans on the two new consumers; Grafana panels; full-suite + live end-to-end verification |

---

## Task 1: Demographic fields + fairness-audit mechanism

Builds the fairness-audit mechanism itself — it does not exist yet (see
"Starting point" above) — grounded in real demographic data the synthetic
generator doesn't currently produce. Rules-engine axis only; Task 3 adds
the fraud-triage axis once `fraud_risk_score` exists.

**Files:**
- Modify: `data-platform/src/canopica_data/synthetic/models.py`
  (`SyntheticPerson` gains `race`/`hispanic_origin`, sampled the same way
  `sex`/`relationship` already are)
- Modify: `data-platform/src/canopica_data/synthetic/fetch_pums.py`
  (+`RAC1P`/`HISP` marginals, same `_weighted_share` pattern the file's
  existing marginals already use)
- Modify: `data-platform/dbt/canopica_warehouse/models/silver/dim_person.sql`
  (+`race`, `+hispanic_origin`, tokenized/classified per this project's
  existing PII-column discipline)
- Create: `data-platform/dbt/canopica_warehouse/models/gold/mart_fairness_audit.sql`
- Create: `data-platform/tests/test_fairness_gate.py`
- Modify: `.github/workflows/ci.yml` (dbt/data-platform job: run the
  fairness gate, fail the job on a disparate-impact ratio regression)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `mart_fairness_audit` — grain `(model, demographic_slice,
  outcome_axis)`; `model = 'rules_engine'` this task, `'fraud_triage'`
  added in Task 3. Built from `dim_person`'s new demographic columns
  joined against `fct_eligibility_determination`.
- Consumes: `fct_eligibility_determination` (existing), `dim_person`
  (existing, this task widens it).

- [x] **Step 1: Confirm PUMS variable names against the pinned vintage**
      (prerequisite above) before writing any parsing code. Done for real:
      fetched the live 2024 PUMS data dictionary text file from the Census
      Bureau, confirmed RAC1P (9 codes) and HISP (24 codes, 01=not
      Hispanic) verbatim before writing `_RACE_MAP`.
- [x] **Step 2: `fetch_pums.py` marginals.** Added `RAC1P`/`HISP`
      distributions via `_weighted_share`; re-ran the script live against
      the real Census Bureau Wyoming 2024 1-Year files and committed the
      regenerated `acs_pums_marginals.json` (real numbers: `WHITE` 0.836,
      `p_hispanic_origin` 0.090, etc. — Wyoming's real demographics, not
      fabricated).
- [x] **Step 3: `SyntheticPerson` sampling.** Done. One design refinement
      beyond the plan's own text: ethnicity is a single Hispanic/Latino
      boolean, not HISP's 24 national-origin subcategories — see the
      implementation plan's own "Starting point" section... actually see
      `fetch_pums.py`'s own comment: keeping the subcategory would be
      exactly the proxy feature constraint 20 excludes.
- [x] **Step 4: `dim_person` silver model.** Done, same tier as `sex`
      (not tokenized — a category value, not an identifier); extended
      `silver.yml`'s `accepted_values` test on `race`, not the PII macro
      (name-based, doesn't match "race"/"hispanic_origin" and shouldn't).
- [x] **Step 5: `mart_fairness_audit`.** Done, plus a real correction found
      testing against real data: an inadequately-sized slice can't anchor
      the reference rate (a real n=1 case swung the whole computation on
      pure luck) — the `reference` CTE now excludes any slice where
      `total_count < 30`, and a new `sample_size_adequate` column makes
      that withholding explicit rather than silent. `fct_household_member`
      (new silver model — bridges `household_key`↔`person_key`, bronze had
      carried this since Phase 1b with no silver model ever built on it)
      was needed to resolve which person's demographics a determination's
      household maps to; joins to the `SELF` household member only.
- [x] **Step 6: CI gate.** Implemented as a dbt **singular test**
      (`tests/gate_no_disparate_impact.sql`), not a separate Python CI
      step — runs automatically inside the existing `dbt build` this
      project's CI job already calls, same "runs in CI and blocks a merge
      on regression" discipline with no new wiring needed. Fails only on
      an *adequately-sized* slice below 0.8, per Step 5's finding.
      `data-platform/tests/test_fairness_gate.py` is the correctness test
      proving this dbt test actually fires (and correctly withholds on a
      tiny slice) — added to `ci.yml`'s explicit dbt/data-platform job test
      list, which enumerates files rather than picking up `-m integration`
      automatically.
- [~] **Step 7: Power BI/Metabase page.** Materialized into the serving
      Postgres `reporting` schema (`materialize.py`'s `GOLD_MARTS`), so
      it's queryable the same way every other mart is — but no dedicated
      Metabase card/dashboard or Power BI TMDL table was built for it
      specifically. Checked first: none of Phase 1b's own
      `mart_payment_accuracy`/`mart_processing_timeliness` have a
      dedicated card/TMDL table either (`provision_metabase.py` only ever
      provisioned one card, for `mart_determination_outcomes`) — this
      mart is at the same real coverage level as its own siblings, not a
      regression. Building an actual fairness dashboard page is real,
      separate work; not done here.
- [x] **Step 8: Tests.** dbt tests on the new mart (all pass — `not_null`
      on every non-nullable column, `accepted_values` on `model`/
      `demographic_axis`). `test_fairness_gate.py`'s fixture
      (`seeded_fairness_dsn`, 30+30+1 rows) proves a deliberately induced
      disparity (30/90% vs 9/30%, ratio 0.333) genuinely fails `dbt
      build`'s exit code, and that a tiny slice (n=1) is genuinely
      withheld regardless of its own ratio — both properties from one
      fixture, both asserted directly against real materialized numbers
      (not just that some test failed). Also verified against the real
      running stack, not just fixtures: rebuilt `infra-api-1` (V22 applied
      cleanly), posted 30 real synthetic households + ran 30 real
      determinations through the live API, confirmed real race/
      hispanic_origin values reached Postgres and the mart. Full suite
      green: api 142+12 (`BUILD SUCCESS`), data-platform 31 non-e2e,
      `ai/` 202 (unaffected), `worker/` 18 (unaffected); `ruff`/`mypy`
      clean. Two pre-existing, unrelated bugs found live and fixed along
      the way (not this task's own code): `fct_audit_event.event_type`'s
      `accepted_values` test was stale against Phase 3's widened
      `AuditEventType` (V18/V19 never updated this list); `materialize_gold`'s
      `GOLD_MARTS` tuple needed this mart added or it would never reach
      the serving layer despite building correctly in DuckDB.
- [x] **Step 9: Full suite + commit.**

---

## Task 2: Fraud Risk Triage — scoring

**Files:**
- Create: `api/src/main/resources/db/migration/V23__fraud_risk_score.sql`
- Create: `api/src/main/resources/db/migration/
  V24__audit_event_type_fraud_flag_raised.sql` (widen `AuditEventType`'s
  CHECK constraint for `FRAUD_FLAG_RAISED` only — **corrected from this
  plan's original text**, which called for a single V25 widening all four
  of this phase's event types at once. This repo's real migration history
  (V16, V18, V20/V21) is strictly "widen once per real need, in landing
  order" — V18's own comment already documents correcting an identical
  pre-widening mistake the Phase 3 plan made once before. Pre-reserving
  V24 here for Task 4's `payment_error_review` while this widening landed
  as V25 would also have broken Flyway's `outOfOrder=false` validation
  (checked: `application.yml` has no such setting) the moment Task 4's
  real V24 file is added afterward. Renumbered V23/V24; Task 3/4/5 each
  widen for their own single event type when they land, and V25 is
  Task 4's real next number, not reserved in advance.)
- Create: `api/src/main/java/canopica/api/fraud/FraudRiskScore.java`,
  `FraudRiskScoreRepository.java`
- Modify: `api/src/main/java/canopica/api/determination/
  JdbcDeterminationService.java` (+`pgmq.send("fraud_scoring", ...)`
  inside the *same* `@Transactional` `determine()` method that already
  sends `correspondence_dispatch` — constraint 17, same transaction, one
  more `pgmq.send` call, not a new transactional path)
- Modify: `api/src/main/java/canopica/api/audit/AuditEventType.java`
- Create: `ai/src/canopica_ai/fraud_triage/features.py`, `score.py`,
  `service.py`
- Create: `ai/tests/test_fraud_triage.py`
- Create: `worker/src/canopica_worker/fraud_scoring_consumer.py`
- Create: `worker/tests/test_fraud_scoring_consumer.py`
- Modify: `worker/src/canopica_worker/main.py`, `config.py`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.fraud_triage.service.score(determination_id: UUID)
  -> FraudScore` (Pydantic: `score: float`, `top_contributing_features:
  list[FeatureContribution]`, `model_version: str`). Sole interface the
  worker consumer calls — never the LLM directly, because there is no
  LLM in this path at all (design doc §2.2: bounded numeric score, not
  free text).
- Consumes: the determination's household/income/verification history
  (read-only), the same data the DMN engine itself read.

- [x] **Step 1: `fraud_risk_score` table.** Done, per design doc §2.8's
      column list, plus a `score >= 0 and score <= 1` check (score.py's own
      min-max normalization guarantees the range) and the same
      reviewed-together check `policy_parameter_proposal` (V14) uses.
- [x] **Step 2: Transactional enqueue.** Done, alongside the existing
      `correspondence_dispatch` send in `determine()`'s own transaction.
- [x] **Step 3: Feature engineering (`features.py`).** Done, the exact four
      features design doc §2.2 names, each a single SQL query against real
      operational tables (income_record's coefficient of variation,
      verification_response's DISCREPANCY rate, household_member rows past
      the household's own earliest effective_from, a percent_rank() window
      query for the percentile). Constraint 20 enforced as a `FEATURE_NAMES`
      tuple plus a real denylist test (`test_fraud_triage.py`), not just a
      comment.
- [x] **Step 4: `IsolationForest` wrapper (`score.py`).** Done. Cadence
      decided: fits fresh against the full case population on every score
      call, not a scheduled batch fit — a deliberate, stated substitution
      against design doc §2.11's shape (real cost recorded in the
      tradeoffs doc's existing Fraud risk triage row), correct and cheap
      at this project's real synthetic-population scale. Attribution
      technique decided: per-feature z-score against the same fitted
      population's own mean/stdev, not isolation-path-length decomposition
      (sklearn exposes no public per-feature path-length API) — comparably
      explainable and deterministically testable.
- [x] **Step 5: Worker consumer.** Done. Decided: every scored case gets a
      `fraud_risk_score` row (Task 3's fairness-audit extension needs the
      full scored population, not only flagged cases, to compute a real
      selection rate); `FRAUD_FLAG_RAISED` fires only at or above a stated,
      not-yet-measured `_REVIEW_THRESHOLD = 0.75` starting default.
- [x] **Step 6: `main.py`/`config.py` wiring.** Done.
- [x] **Step 7: Tests.** Done. `test_fraud_triage.py`: the denylist check,
      plus a deliberately anomalous case (income reported three wildly
      different ways, every verification a discrepancy, constant
      composition change) scoring above every typical case in the same
      population, and a degenerate single-case population scoring exactly
      0.0. `test_fraud_scoring_consumer.py`: three real end-to-end cases
      against a real local Postgres (above-threshold persists + flags,
      below-threshold persists without flagging, a processing failure
      leaves the message for pgmq's own retry).
- [x] **Step 8: Full suite + commit.** Full suite green: api (142 + 12
      rules-engine, `BUILD SUCCESS`), data-platform (31 non-e2e,
      unaffected), `ai/` (206 non-e2e, +4), `worker/` (21, +3); `ruff`/
      `mypy` clean. One real bug caught only by running the full suite:
      `AbstractPostgresTest` (Java) had never created the `fraud_scoring`
      pgmq queue, so all 21 tests through a real Spring context calling
      `determine()` failed with `bad SQL grammar [select pgmq.send(...)]`
      until fixed.

---

## Task 3: Fraud Risk Triage — review + fairness extension

**Files:**
- Create: `api/src/main/java/canopica/api/api/FraudReviewController.java`
- Modify: `api/src/main/java/canopica/api/config/SecurityConfig.java`
  (`SUPERVISOR`-scoped, same `hasRole("SUPERVISOR")` pattern already used
  for the parameter-publish endpoint's `ADMIN` scoping)
- Create: `ui/src/pages/FraudReviewPage.tsx`
- Modify: `data-platform/dbt/canopica_warehouse/models/gold/
  mart_fairness_audit.sql` (+`model = 'fraud_triage'` axis, sourced from
  `fraud_risk_score` joined to the widened `dim_person`)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `GET /api/fraud/review-queue` (`SUPERVISOR`-scoped, ordered by
  score descending), `POST /api/fraud/{scoreId}/confirm`, `POST /api/fraud/
  {scoreId}/clear` — sets `review_outcome`, appends `FRAUD_FLAG_REVIEWED`.
  Neither endpoint touches the determination, the benefit amount, or any
  notice (constraint 19) — the review outcome is a case-management fact
  about the flag itself, nothing else.

- [x] **Step 1: Review-queue + confirm/clear endpoints.** Done.
      `SecurityConfig` gained a `/api/fraud/**` -> `hasRole("SUPERVISOR")`
      matcher, same narrowest-existing-role reasoning `/api/policy/**`
      already uses -- no data-driven caseload check, since the queue is
      deliberately cross-caseload. `FraudRiskScore` gained intent-named
      `confirmRisk()`/`clear()` transitions (not setters), mirroring
      `Notice`'s own `approveAndSend`/`reject` precedent -- a second
      reviewer cannot re-decide an already-reviewed flag.
      `FraudReviewService` owns the one Java write to `fraud_risk_score`
      and appends `FRAUD_FLAG_REVIEWED`; a new
      `V25__audit_event_type_fraud_flag_reviewed.sql` widens the
      constraint for this task's own single new event type, continuing
      the corrected per-real-need numbering Task 2 established.
- [x] **Step 2: `FraudReviewPage.tsx`.** Done. **Real gap found and
      closed first**: the frontend's own `Role` type
      (`ui/src/auth/AuthContext.tsx`) only ever distinguished
      `CUSTOMER`/`WORKER`/`ADMIN` -- a real SUPERVISOR Keycloak realm role
      was silently collapsing into `WORKER` at the UI layer, meaning no
      page could ever have been shown to supervisors only. This wasn't
      optional for this step: without fixing it, "SUPERVISOR-scoped UI"
      was structurally impossible to build. Widened `Role` to a real
      fourth value, `roleFor()` to recognize the realm role, `NavRail`'s
      `LINKS_FOR` to give SUPERVISOR a strict superset of WORKER's own
      links (matching the backend's own `hasAnyRole("WORKER",
      "SUPERVISOR")` pattern on most case endpoints) plus the new Fraud
      review link, and `App.tsx`'s `HOME_FOR` to send a supervisor to the
      same `/dashboard` a worker lands on. Page itself mirrors
      `NoticeReviewPage.tsx`'s shape; top contributing features render as
      a structured list (name + z-score), never a narrated sentence.
- [x] **Step 3: `mart_fairness_audit` extended.** Done. A real
      prerequisite gap found first: `fraud_risk_score` had no bronze/
      silver path at all (Phase 3's `document`/`notice` tables never
      needed one either, so nothing existed to copy) -- added to
      `extract.py`'s `ALL_TABLES` and `sources.yml`, plus a new
      `fct_fraud_risk_score.sql` silver model (same latest-by-
      `_ingested_at` dedup `fct_eligibility_determination.sql` already
      uses, since this is a mutable row). "Favorable" for this axis is
      defined as NOT flagged (`score < 0.75`, the same threshold
      `fraud_scoring_consumer.py`'s own `_REVIEW_THRESHOLD` uses,
      duplicated with a cross-reference comment since dbt SQL and `ai/`
      Python share no config mechanism) -- kept as "the good outcome for
      the person," the same polarity `rules_engine`'s own
      "favorable = eligible" already uses, so a low
      `disparate_impact_ratio` means the same thing on both axes.
- [x] **Step 4: Accessibility pass.** Done -- `axe` check passes with no
      violations (`FraudReviewPage.test.tsx`'s own last test).
- [x] **Step 5: Tests.** Done. Java (`FraudReviewControllerTest`, 4
      tests): a `WORKER` token gets 403 on the review queue; the queue
      orders unreviewed flags by score descending and excludes an
      already-reviewed one; confirm sets `review_outcome`, appends
      `FRAUD_FLAG_REVIEWED`, and is asserted to leave the flagged
      determination's own `benefit_amount` unchanged; clear sets
      `review_outcome` and does not raise a second `FRAUD_FLAG_RAISED`.
      Vitest/RTL (`FraudReviewPage.test.tsx`, 8 tests): queue renders,
      empty state, selecting shows score/features, confirm/clear call the
      right endpoint and remove the item, a failed confirm shows an
      inline error and keeps the item, accessibility. dbt
      (`test_fairness_gate.py`, extended): the same `seeded_fairness_dsn`
      fixture now also seeds a `fraud_risk_score` row per determination
      mirroring each one's own `eligible` polarity onto `not_flagged`,
      inducing the identical 0.3/0.9 disparity on the `fraud_triage` axis
      -- proven against real materialized numbers, not just that dbt
      build failed.
- [~] **Step 6: Live manual check.** Not done this session -- every
      other verification here is real (a real Postgres, real Keycloak
      tokens, a real dbt build against real seeded data, no mocks), but
      the browser walkthrough itself (sign in as `supervisor.robin`,
      click through the real queue, confirm/clear a real flagged case)
      was deferred to keep this task's own commit boundary from growing
      further -- stated honestly rather than skipped silently. Real
      follow-up work, not a gap papered over.
- [x] **Step 7: Full suite + commit.** Full suite green: api (134 + 12
      rules-engine, `BUILD SUCCESS`, +4 for `FraudReviewControllerTest`),
      data-platform (31 non-e2e, unaffected row counts confirmed),
      `ai/`/`worker/` unaffected (this task touched no Python), UI (66,
      +8 for `FraudReviewPage.test.tsx`); `ruff`/`mypy`/`oxlint`/`tsc`
      all clean.

---

## Task 4: QC / Payment Error Rate Assistant — sampling

**Files:**
- Create: `api/src/main/resources/db/migration/V26__payment_error_review.sql`,
  `V27__audit_event_type_qc_discrepancy_flagged.sql` (**done: renumbered
  from the plan's original `V25`/single-file guess -- Task 3 claimed V25
  for `audit_event_type_fraud_flag_reviewed.sql` first, and the widen-CHECK
  step is its own migration per Task 2/3's own corrected "one real need per
  file" numbering, not folded into the table's own file**)
- Create: `api/src/main/java/canopica/api/qc/PaymentErrorReview.java`,
  `PaymentErrorReviewRepository.java`, `QcSamplingService.java`
- Create: `api/src/main/java/canopica/api/api/QcController.java` (this
  task: an internal, `ADMIN`-scoped sample-trigger endpoint for Airflow to
  call; Task 5 adds the human review-queue endpoints)
- Create: `ai/src/canopica_ai/qc_assistant/draft.py`, `validate.py`,
  `service.py` (**done: split into three files, not `summarize.py`+
  `service.py` as planned -- matches `correspondence/`'s own real
  draft/validate/service split once this capability turned out to need
  the identical LLM-draft-then-deterministic-grounding-check shape, which
  wasn't obvious until the grounding requirement in Step 8 below was
  actually implemented**)
- Create: `ai/tests/test_qc_assistant.py`
- Create: `worker/src/canopica_worker/qc_summary_consumer.py`
- Create: `worker/tests/test_qc_summary_consumer.py`
- Create: `data-platform/dbt/canopica_warehouse/models/silver/
  fct_payment_error_review.sql` (**done: real deviation from the plan's
  `models/staging/stg_payment_error_review.sql` -- no `staging/` layer
  exists anywhere in this warehouse; every other operational-table
  ingestion, `fct_fraud_risk_score.sql` included, uses the real silver
  `fct_` pattern, so this follows that actual precedent instead of
  introducing a one-off directory convention**)
- Modify: `data-platform/dbt/canopica_warehouse/models/gold/
  mart_payment_accuracy.sql` (real `reviewed`/`payment_error_amount`,
  sourced from `fct_payment_error_review` instead of the current hardcoded
  `false`/`null`)
- Modify: `infra/airflow/dags/canopica_pipeline_dag.py` (+a scheduled task
  calling the sample-trigger endpoint)
- Modify: `identity/realm-export/canopica-workers-realm.json` (**done, not
  in the plan's original file list -- a real prerequisite gap found while
  implementing Step 5: nothing in this repo could authenticate a scheduled,
  non-human caller as ADMIN. `test-worker`'s own name/description already
  reserve it for pytest/Maven test suites; added `canopica-airflow`, a real
  `client_credentials` service-account client, rather than repurpose a
  client documented as test-only**)
- Modify: `docs/STATUS.md`

**Why this needs an operational table, not just a dbt computation** — a
real finding worth stating: `reproduce()` only runs in the JVM (DMN
evaluation is Java-only; dbt/DuckDB has no path to call it), and a QC
reviewer's confirm/dismiss decision (Task 5) is durable human-authored
state that a nightly-rebuilt gold mart cannot hold — gold gets overwritten
on every `dbt build`, so a human's review outcome has nowhere to persist
if it only ever lived there. `payment_error_review` is the operational
table that actually holds it; `mart_payment_accuracy` reads from it
through the normal bronze→silver→gold path, same as every other
operational table this warehouse reports on.

**Interfaces:**
- Produces: `canopica_ai.qc_assistant.service.summarize(determination_id:
  UUID, original_amount: Decimal, reproduced_amount: Decimal) -> str`
  (**done: returns the summary text directly rather than a
  `DiscrepancySummary` wrapper — there was nothing else for that type to
  carry once the grounding check lives in `validate.py` as its own
  gate, not a field on the return value**, composed only from the diff and
  both evaluations' own trace records — constraint 21, via a bundled
  `DiscrepancyContext`). Called by the worker's `qc_summary_consumer.py`,
  never directly by Java.
  `POST /api/internal/qc/run-sample` (`ADMIN`-scoped, Airflow-triggered):
  samples N recently decided determinations, calls `DeterminationService.
  reproduce()` on each, diffs against the stored `benefitAmount`, writes a
  `payment_error_review` row for every sampled case (not only the ones
  with a nonzero diff — an unflagged sample is itself evidence the mart
  needs), and enqueues `qc_summary` only for rows with a nonzero diff.

- [x] **Step 1: `payment_error_review` table.** Done: `id`,
      `determination_id`, `original_amount`, `reproduced_amount`,
      `error_amount`, `reproduced_trace jsonb` (**not in the original plan
      -- added because `reproduce()` persists nothing itself, so this is
      the only place the reproduction's own `SnapDecision.trace()` can
      live for Step 6's grounding check to read back later**), `ai_summary`,
      `sampled_at`, `reviewed_by`, `reviewed_at`, `review_outcome`
      (`CONFIRMED_ERROR`/`DISMISSED`/null while pending), `unique
      (determination_id)` (race-safety net behind the sampling query's own
      exclusion, same reasoning V23's own unique-ish review-queue index
      note gives).
- [x] **Step 2: `QcSamplingService`.** Done. 10% of the eligible/unsampled
      population in a 30-day lookback (`DEFAULT_SAMPLE_RATE`, a stated,
      unmeasured default like `_REVIEW_THRESHOLD`'s own precedent --
      chosen well above the real federal SNAP QC program's roughly
      1-in-1000 rate because this project's own data volume would sample
      zero cases at that rate). Calls the existing
      `DeterminationService.reproduce()` for each — no new DMN-evaluation
      code, confirmed against the "starting point" finding above. Writes
      one `payment_error_review` row per sampled case. **A real Spring AOP
      bug caught and fixed before any test was written against it**: the
      original `runSample()` called `this.sampleOne(...)` directly, which
      is plain Java self-invocation and bypasses the `@Transactional`
      proxy entirely -- fixed via `@Lazy` self-injection so Step 3's own
      guarantee actually holds.
- [x] **Step 3: Transactional enqueue.** Done, inside `sampleOne` (now
      routed through the `self` proxy per Step 2's own fix) — for rows
      with a nonzero `error_amount`, `pgmq.send('qc_summary',
      {payment_error_review_id})` inside the same transaction as that
      row's insert.
- [x] **Step 4: `run-sample` endpoint.** Done. `ADMIN`-scoped via
      `SecurityConfig`'s `/api/internal/qc/**` matcher, same posture as
      `/api/policy/**`. Accepts an optional `sampleSize` query param,
      defaulting to `QcSamplingService.computeDefaultSampleSize()`.
- [x] **Step 5: Airflow task.** Done — `run_qc_sample`, independent of the
      extract/dbt/materialize chain (it writes to the operational database
      directly, not the warehouse), on the same `@hourly` cadence. **Real
      prerequisite gap found and fixed**: nothing in this repo could
      authenticate a scheduled caller as ADMIN — added `canopica-airflow`,
      a real `client_credentials` service-account client, rather than
      reuse `test-worker`'s password grant (reserved by its own
      name/description for test suites).
- [x] **Step 6: `draft.py`/`validate.py` + worker consumer.** Done, split
      from the plan's single `summarize.py` into the draft/validate/service
      shape `correspondence/` already established, once the grounding
      requirement made that split the obviously correct one. Composed only
      from the diff and both evaluations' own trace records (constraint
      21) via a bundled `DiscrepancyContext`, not 6-8 positional
      parameters (a real `ruff` finding, fixed by the bundle). Consumer
      writes `ai_summary` back onto the `payment_error_review` row,
      appends `QC_DISCREPANCY_FLAGGED` to the audit log, deletes the
      message.
- [x] **Step 7: `fct_payment_error_review` + `mart_payment_accuracy`
      update.** Done (real silver-layer naming deviation — see the file
      list note above). The mart's `reviewed`/`payment_error_amount`
      columns now come from a left join to this silver model — a
      determination never sampled still shows `reviewed = false`/`null`,
      exactly matching the earlier placeholder default; a sampled case
      shows the real diff.
- [x] **Step 8: Tests.** Done. Java: `QcSamplingServiceTest` (5 tests) —
      since `eligibility_determination` is append-only, the mismatched-
      parameter-set scenario reuses a genuine determination's own real
      `input_snapshot` and inserts a second row against FY2026's real,
      different parameters (not a synthetic fixture) to force a genuine
      `reproduce()` diff; `QcControllerTest` (3 tests) confirms
      `ADMIN`-only. `ai/`: `test_qc_assistant.py` (7 tests) grounds a
      discrepancy summary in the actual diff/trace fields via the same
      "citation-existence"-style deterministic check Phase 2/3 already use
      elsewhere, plus an `e2e` class proving the real three-table trace
      join. dbt: `fct_payment_error_review`'s own `relationships` test
      (to `fct_eligibility_determination`) is the real referential-
      integrity check `mart_payment_accuracy`'s new join depends on,
      confirmed by `test_dbt_build.py`.
- [x] **Step 9: Full suite + commit.** Full suite green: api (142,
      `BUILD SUCCESS`, +8), data-platform (31), `ai/` (213, +7), `worker/`
      (24, +3), UI (66, unaffected); `ruff`/`mypy`/`oxlint`/`tsc` clean.
      Live Airflow trigger not manually exercised this session — see
      STATUS.md's own verification-log row.

---

## Task 5: QC review UI

**Files:**
- Modify: `api/src/main/java/canopica/api/api/QcController.java`
  (+review-queue, +confirm, +dismiss endpoints)
- Modify: `api/src/main/java/canopica/api/qc/PaymentErrorReviewRepository.java`
- Create: `ui/src/pages/QcReviewPage.tsx`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `GET /api/qc/review-queue` (`SUPERVISOR`-scoped, unreviewed
  rows with a nonzero `error_amount`), `POST /api/qc/{reviewId}/confirm`,
  `POST /api/qc/{reviewId}/dismiss` — sets `review_outcome`, appends
  `QC_REVIEW_COMPLETED`. Neither endpoint corrects the original
  determination or its benefit amount (constraint 19) — QC flags an
  estimate of error, it does not fix one.

- [ ] **Step 1: Review-queue + confirm/dismiss endpoints.**
      `SUPERVISOR`-scoped, same pattern as Task 3's fraud-review
      endpoints.
- [ ] **Step 2: `QcReviewPage.tsx`.** Shows the original amount, the
      reproduced amount, the diff, and the AI-drafted summary (visibly
      marked advisory, same `AiAdvisoryBadge` component the UI
      modernization work already built for this exact purpose);
      confirm/dismiss actions.
- [ ] **Step 3: Accessibility pass.**
- [ ] **Step 4: Tests.** Java: caseload-agnostic `SUPERVISOR` scoping
      (QC review isn't tied to a single caseload the way fraud review's
      case-level access is — confirm the intended scope at implementation
      time); confirm/dismiss never writes to `eligibility_determination`.
      Vitest/RTL: page renders the diff and summary, confirm/dismiss call
      the right endpoint.
- [ ] **Step 5: Live manual check.**
- [ ] **Step 6: Full suite + commit.**

---

## Task 6: Case SLA/Compliance Monitor

**Files:**
- Create: an `AtRiskCaseQuery` (or similarly named) class in an existing
  `api/` package (`caseload/` or `intake/` — decide at implementation time
  based on which existing service already reads `program_request`/
  `verification` rows this closely)
- Create: `api/src/main/java/canopica/api/api/SlaMonitorController.java`
- Create: `ai/src/canopica_ai/sla_monitor/prioritize.py`, `summarize.py`,
  `service.py`
- Create: `ai/tests/test_sla_monitor.py`
- Create: `ui/src/pages/SlaMonitorPage.tsx`
- Modify: `infra/airflow/dags/canopica_pipeline_dag.py` (+an
  intra-day-frequency task refreshing stall-reason summaries — same
  batch-then-worker-summarize shape as Task 4's QC job, not a third
  distinct AI-invocation pattern; decide the exact refresh cadence at
  implementation time, informed by "current within the workday" from the
  design doc rather than real-time-per-page-load)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `GET /api/sla/at-risk-queue` (`SUPERVISOR`-scoped) — live
  query against `program_request` rows in `SUBMITTED`/`PENDING_
  VERIFICATION` status, aged against SNAP's 7-day-expedited/30-day
  standard from `requested_on` (the same standard `mart_processing_
  timeliness` already applies to decided cases, applied here to pending
  ones), ordered by days-remaining ascending. Each row's stall-reason
  string is pre-generated on the refresh cadence above, not computed
  per-request — keeps the endpoint itself a plain, fast SQL query with no
  LLM call on the request path.

- [ ] **Step 1: At-risk query.** Operational, not a mart (design doc
      §2.4's explicit reasoning: same-day currency a nightly pipeline
      can't give) — ages `program_request` rows still pending against the
      existing 7/30-day standard.
- [ ] **Step 2: `prioritize.py`.** Plain deterministic ranking (days
      remaining, ascending) — explicitly not an LLM's job, per design doc
      §2.4.
- [ ] **Step 3: `summarize.py`.** One-line stall reason per at-risk case,
      grounded in that case's own outstanding `verification` rows and
      recent audit-trail entries (e.g. "awaiting INCOME verification, due
      in 2 days, last worker action 6 days ago") — composed from real
      fields, never invented, same discipline as Task 4's QC summary.
- [ ] **Step 4: Refresh job.** The Airflow task calls `service.
      summarize` for the current at-risk set on its own cadence,
      writing results to a small table the `at-risk-queue` endpoint reads
      from directly (no LLM call on the live request path).
- [ ] **Step 5: `SlaMonitorPage.tsx`.** `SUPERVISOR`-scoped queue view,
      days-remaining prominent, stall reason visibly AI-generated
      (`AiAdvisoryBadge`).
- [ ] **Step 6: Accessibility pass.**
- [ ] **Step 7: Tests.** Java: at-risk query correctly ages a fixture set
      of pending requests against the 7/30-day standard, matches what
      `mart_processing_timeliness` would compute for the same case once
      decided (a real cross-check, not just an isolated unit test).
      `ai/`: a stall-reason summary references only real
      verification/audit fields from its fixture case (deterministic
      grounding check). Vitest/RTL: queue renders sorted by urgency.
- [ ] **Step 8: Live manual check.**
- [ ] **Step 9: Full suite + commit.**

---

## Task 7: Caseworker SOP Copilot

**Files:**
- Create: `ai/src/canopica_ai/sop_copilot/corpus/*.md` (authored SOP
  documents: new application, reported change, renewal — the three case
  types design doc §2.5 names)
- Create: `ai/src/canopica_ai/sop_copilot/corpus/index.py` (mirrors
  `policy_intelligence/corpus/index.py`'s indexing pipeline structurally —
  same chunking/embedding approach, a **separate** OpenSearch index)
- Create: `ai/src/canopica_ai/sop_copilot/retrieval.py`, `service.py`,
  `api.py` (FastAPI, same pattern as `policy_intelligence/qa/api.py` — a
  synchronous, request/response capability, not a queue consumer)
- Create: `ai/tests/test_sop_copilot.py`
- Create: `ui/src/pages/SopCopilotPage.tsx`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `POST /sop-copilot/ask` on the Python AI service (same
  FastAPI-app-per-capability shape `policy_intelligence` already uses),
  called synchronously from Java the same way `HttpRuleAuthoringClient`
  already calls `rule-authoring/propose` — a new `HttpSopCopilotClient`
  (or similarly named) following that exact pattern, not a new
  Java-to-Python integration mechanism.

- [ ] **Step 1: Author the SOP corpus.** Realistic but explicitly
      fictional procedure documents for new application / reported change
      / renewal, stated as authored (not sourced) the same way this
      project's synthetic applicant data already is — a code comment or
      corpus README saying so plainly, matching design doc §2.5's own
      framing.
- [ ] **Step 2: Index into a separate OpenSearch index.** Same hybrid
      BM25+k-NN, RRF-fused, cross-encoder-reranked pipeline `policy_
      intelligence`'s corpus already uses — reused, not reimplemented —
      pointed at a distinct index name so SOP and policy retrieval never
      cross-contaminate.
- [ ] **Step 3: Retrieve→generate service.** Same abstention discipline as
      Policy Q&A: a weak corpus match returns "insufficient information,"
      never an improvised procedure (design doc §2.5's stated failure
      mode: a wrong SOP answer is a caseworker doing the wrong next step
      on a real case).
- [ ] **Step 4: `HttpSopCopilotClient` + Java endpoint.** Worker- (not
      only supervisor-) facing, since this is a caseworker tool per the
      roadmap's own framing — confirm the intended role scope at
      implementation time against `SecurityConfig.java`'s existing
      `WORKER`/`SUPERVISOR` pattern.
- [ ] **Step 5: `SopCopilotPage.tsx`.** A simple ask/answer UI, citations
      to the specific SOP document/section retrieved, same provenance
      display Policy Q&A's own UI already established.
- [ ] **Step 6: Accessibility pass.**
- [ ] **Step 7: Tests.** `ai/`: a question matching real corpus content
      retrieves and answers correctly with citations; a question outside
      the corpus's scope abstains rather than improvising (same shape as
      Policy Q&A's own eval-style tests). Java: the HTTP client integration
      test (same pattern `HttpRuleAuthoringClient`'s own tests already
      use). Vitest/RTL: ask/answer flow renders citations.
- [ ] **Step 8: Live manual check.**
- [ ] **Step 9: Full suite + commit.**

---

## Task 8: SOP Process-Improvement Mining

**Files:**
- Modify: `ai/src/canopica_ai/analytics_copilot/metric_catalog.py`
  (+time-to-resolution by case type, +rejection-reason frequency from
  `mart_determination_outcomes`, +notice-rejection rate from
  `notice.status`)
- Modify: `ai/src/canopica_ai/analytics_copilot/service.py` or a new
  narrow module (narrative-synthesis prompt/logic for turning a metric
  query result into a process-improvement suggestion)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Extends the existing Analytics Copilot MCP tool surface
  (`mcp_server.py`/`tools.py`) with the new metrics — no new endpoint, no
  new authorization mechanism. Authorization stays resolved at
  tool-exposure time, before query compilation, exactly as the roadmap's
  existing Analytics Copilot decision already states.

- [ ] **Step 1: New metrics in `metric_catalog.py`.** Named, governed
      MetricFlow metrics — not raw SQL the LLM writes itself, same
      grounding discipline the whole Analytics Copilot mechanism already
      enforces.
- [ ] **Step 2: Narrative-synthesis extension.** The LLM's job stays
      "synthesize a narrative suggestion from metrics it queried through
      the existing tool-calling path" — no new tool-calling loop, no
      write path (constraint 22).
- [ ] **Step 3: Tests.** A copilot query naming one of the new metrics
      resolves through the existing tool-exposure/authorization path
      unchanged; the resulting narrative references only values the tool
      call actually returned (grounding check, same shape as every other
      AI capability's own test in this repo).
- [ ] **Step 4: Full suite + commit.**

---

## Task 9: Data-quality anomaly detection

**Files:**
- Modify: `data-platform/dbt/canopica_warehouse/packages.yml`
  (+`elementary-data`)
- Create: `ai/src/canopica_ai/data_quality/elementary_ingest.py`,
  `root_cause.py`, `service.py`
- Create: `ai/tests/test_data_quality.py`
- Modify: `data-platform/src/canopica_data/serving/materialize.py`
  (+`data_quality_incident` table, data-platform-owned per design doc
  §2.8 — not an `api/` Flyway migration, since this is a serving-layer
  table the pipeline itself writes, not an operationally-transacted one)
- Modify: `.github/workflows/ci.yml` (dbt/data-platform job: run Elementary
  after `dbt build`, same job Task 1's fairness gate already runs in)
- Modify: a Power BI/Metabase page (small `data_quality_incident` view)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.data_quality.service.summarize(model_name: str,
  test_or_check_name: str, failing_row_sample: ..., historical_baseline:
  ...) -> str` — a plain-language root-cause summary, called by a small
  pipeline step after `dbt build`/Elementary run whenever a test fails or
  an anomaly fires, writing the result to `data_quality_incident`.

- [ ] **Step 1: Elementary setup.** Add the package, configure its dbt
      models/macros per its own current setup docs (checked at
      implementation time, per the prerequisite above), enable anomaly
      detection and schema-change alerts on this project's existing
      silver/gold models.
- [ ] **Step 2: `data_quality_incident` table.** Per design doc §2.8:
      `id`, `source` (`dbt_test`/`elementary`), `model_name`, `test_or_
      check_name`, `detected_at`, `summary`, `raw_context` (jsonb).
- [ ] **Step 3: Failure→summary pipeline step.** On a `dbt test` failure
      or an Elementary anomaly, gather structured context (model, test,
      a failing-row sample, Elementary's own historical baseline) and call
      `service.summarize`; insert the resulting row. Human reads and
      investigates — nothing auto-remediates a pipeline failure
      (constraint 19's spirit, applied to this component too).
- [ ] **Step 4: Reporting page.** `data_quality_incident` rendered as a
      small Metabase/Power BI page — same "gate proves enforcement, report
      proves visibility" pattern as Task 1's fairness page.
- [ ] **Step 5: CI wiring.** Elementary's own check run added to the
      existing dbt/data-platform CI job — a genuine anomaly-detection
      failure should be visible in CI output, not just locally.
- [ ] **Step 6: Tests.** A deliberately broken fixture model triggers a
      dbt test failure and a `data_quality_incident` row with a summary
      that references the real failing test/model names, not invented
      ones.
- [ ] **Step 7: Full suite + commit.**

---

## Task 10: Observability & Phase 4 wrap-up

**Files:**
- Modify: `worker/src/canopica_worker/fraud_scoring_consumer.py`,
  `qc_summary_consumer.py` (+`traced_queue_cycle` spans, same shape Phase
  3 Task 8 built for the first two queues — a third and fourth call site
  of an existing pattern, no new instrumentation code)
- Modify: Grafana provisioning (+a panel: `fraud_risk_score` rows scored
  per day, review-queue backlog depth; +a panel for `payment_error_review`
  sample/backlog)
- Modify: `docs/STATUS.md` (Phase 4 definition-of-done verification)
- Modify: `README.md` (architecture diagram — two new queues, the new
  fairness/QC/SLA/SOP/data-quality components)

- [ ] **Step 1: Worker spans.** `traced_queue_cycle` around both new
      consumers' read/dispatch/delete-or-archive cycles.
- [ ] **Step 2: Grafana panels.** Fraud-scoring throughput and review
      backlog; QC-sampling throughput and review backlog — same
      operational-visibility reasoning as Phase 3's own pgmq panel.
- [ ] **Step 3: End-to-end verification.** Run for real, against the live
      local stack, not mocked: a determination commit → fraud score →
      review-queue → confirm/clear path; a QC sample run → discrepancy →
      review-queue → confirm/dismiss path; the SLA at-risk queue against a
      fixture set of aged pending cases; a SOP Copilot question against
      the real corpus; an Analytics Copilot query against one of Task 8's
      new metrics; a deliberately broken dbt fixture producing a real
      `data_quality_incident` row. Same "verified for real" bar every
      earlier phase's own definition of done already holds to.
- [ ] **Step 4: Full suite, push, CI-confirm.**

---

## Phase 4 definition of done

- [ ] All 10 tasks committed, each with its own green full-suite run.
- [ ] Every task's CI job is CI-confirmed green — not just locally
      verified, per this project's established "CI-confirmed" bar.
- [ ] The fairness CI gate genuinely fails on an induced disparity in both
      the rules-engine and fraud-triage axes (Task 1/3's own tests prove
      this, not just that the gate exists).
- [ ] A live, manual walkthrough of every component (Task 10 Step 3) is
      run for real before this phase is called done.
- [ ] `docs/STATUS.md` reflects Phase 4 as done, at the same task
      granularity Phase 1b/2/3 already use.
- [ ] The README's architecture diagram updates to show the two new
      queues and this phase's components, per CLAUDE.md's same-commit
      convention for that diagram.

## Deferred out of Phase 4, on purpose

A supervised fraud classifier (once/if real labeled outcome data exists —
this project's synthetic data structurally can't support it now); a
chat-ops (Slack) integration for data-quality alerts (§2.7's own fork —
scope this project has no other reason to carry); SOP mining writing
directly to a corpus/document store (§2.6's own scope boundary — an SOP
change is a human/process action, not an app write path this system
should ever gain) — all per design doc §2.12's own "considered,
deliberately deferred" list. Phase 5 (cloud realization demos) is out of
this plan's scope entirely, per this project's established one-phase-per-
plan convention.
