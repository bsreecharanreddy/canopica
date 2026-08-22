# Canopica — Tech Stack, Production Equivalents, and Deliberate Trade-offs

Status: approved
Date: 2026-08-21

## 1. Why this document exists

Every technology choice in Canopica is one of three things:

1. **Identical** to what a real production eligibility system would use.
2. **Same-shape** — a different product, but the same concept, interface,
   and skills; migrating is configuration, not a rewrite.
3. **Substituted** — a deliberate downgrade made because the real thing
   costs money, requires a government tenant, or requires a team.

Portfolio projects usually blur these together and quietly imply the first
category. This document separates them explicitly, because knowing *which
compromises you made and what they cost* is a more useful signal about an
engineer than a stack list is.

## 2. Stack map

Fidelity column: **=** identical · **≈** same-shape · **~** substituted.

### Application tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| API | Spring Boot (Java) | Spring Boot / Jakarta EE on an app server; .NET in some shops | **=** | Nothing. Same framework, same patterns. |
| Web UI | React (one app, role-gated views) | React or Angular, usually **two separate applications** — a public-internet citizen portal and an intranet worker portal, with different threat models and release cadences | **≈** | Split into two builds; citizen app behind WAF/CDN, worker app network-restricted. |
| API edge | Direct to service | API gateway (Azure APIM, Apigee), WAF, rate limiting, mutual TLS between tiers | **~** | Insert gateway; no application code change. |
| Identity — authentication | Keycloak, self-hosted OIDC, two realms | PingFederate / ForgeRock / Entra External ID for citizens; enterprise SSO (SAML/OIDC) + PIV/CAC for staff | **≈** | Swap the OIDC provider. Spring Security config changes; application code does not. |
| Identity — *proofing* | None | **This is the real gap.** Citizen portals federate to a NIST IAL2 identity-proofing service (Login.gov, ID.me) that verifies a human is who they claim before an account exists | **~** | Genuinely absent here — see §4.3. Keycloak authenticates an account; it does not prove an identity. |
| Authorization | Spring Security RBAC + explicit `CASE_ASSIGNMENT`-scoped row filtering; sensitive cases are flagged and logged, not sealed | Same, plus attribute-based policies, true sensitive-case sealing (VIP/employee/domestic-violence cases, blocked without an override workflow), and periodic access recertification | **≈** | Add recertification workflow and a real sealing/override flow; core assignment-scoped model is the same. |

### Rules tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Rules engine | DMN 1.x decision tables on Drools/KIE (`kie-dmn`), embedded in the Spring Boot service | Commercial policy-automation suites (Oracle Policy Automation, IBM ODM, Red Hat Decision Manager, FICO Blaze) | **≈** | DMN is an OMG standard several of those products implement — and Red Hat Decision Manager is the commercially supported build of this exact engine, so that particular migration is a support contract rather than a port. Rules stay authored as data, not code, either way; that property is what transfers, not the vendor. |
| Rule authoring | Decision tables in the repo, reviewed via pull request | A policy-analyst-facing authoring GUI, with a separate approval workflow and a rules release cycle decoupled from application releases | **~** | No GUI here. PR review stands in for the approval workflow — the governance concept survives, the tooling doesn't. |
| Policy versioning | Effective-dated parameter sets, version stamped on every determination | Same — mandatory, because federal thresholds change annually and determinations must be reproducible as-of their decision date | **=** | Nothing. This is not a place to compromise; see the roadmap doc. |

### Data tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Operational store | Postgres | Oracle (still dominant in legacy state systems), SQL Server, or Postgres | **≈** | Dialect differences in DDL only. |
| PII protection (silver tokenization) | `pii_token` vault table, `pgcrypto`-encrypted, narrow-RLS'd; detokenization is a separate audited call (Phase 1b) | A dedicated tokenization product or HSM-backed envelope encryption, running as an out-of-band service with its own credential | **~** | See §4.15 — the vault lives in the same database and failure domain as the data it protects, unlike a real out-of-band vault. |
| Transformation | dbt, medallion (bronze/silver/gold) | dbt on Databricks/Snowflake/Fabric — or, in older systems, Informatica / DataStage / Ab Initio | **=** | The dbt project is portable as-is. |
| Compute engine | DuckDB (local, in-process) | Spark on Databricks, Fabric, or Synapse | **≈** | A dbt profile swap (`dbt-duckdb` → `dbt-databricks`). Model SQL is unchanged. |
| Table format | Delta Lake, via the open-source `deltalake` library (no Spark) | Delta Lake on Databricks/Fabric, or Iceberg | **=** | Same on-disk format, byte for byte. |
| Object storage | MinIO (S3-compatible) | ADLS Gen2 / S3, with lifecycle policies, immutability holds, and CMK encryption | **≈** | Endpoint + credential change; lifecycle/retention policies added. |
| Serving layer | Postgres, materialized gold | Fabric Warehouse, Synapse Dedicated SQL Pool, Azure SQL MI, Exadata | **≈** | Connection change; partitioning and distribution keys become real work at volume. |
| Orchestration | Airflow (Docker Compose) | Airflow (managed), Azure Data Factory, Fabric Data Factory — or **Control-M / AutoSys**, which remain very common in government | **≈** | DAG concepts transfer; scheduler product does not. |
| Ingestion pattern | Nightly/on-demand batch extract (Python job, Postgres → Delta bronze) | Change Data Capture — Debezium (or a managed CDC connector: Fivetran, Azure Data Factory's CDC feature) reading the write-ahead log and streaming each change as it commits | **~** | Requires a broker to stream into (Kafka Connect, typically) — the same class of infrastructure this project already declined to stand up for messaging; see the Messaging tier below and §4.12. Bronze's shape is unaffected either way; only how continuously it fills. |
| Data volume | Thousands of synthetic records | Millions of persons, tens of millions of benefit-month rows, decades of retained history | **~** | See §4.1 — this is the single largest fidelity gap in the data tier. |

### Reporting tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Semantic model | Model-as-code (TMDL), version-controlled | Same model, hosted on Fabric/Power BI Premium capacity | **=** | Deploy target only. |
| Interactive reports | Power BI (free tier / Service) + a containerized OSS dashboard so the repo renders for anyone who clones it | Power BI Premium capacity with row-level security, gateways, deployment pipelines, and workspace governance | **≈** | RLS enforcement, refresh scheduling, and capacity management are all absent here. |
| Regulatory reports | Not built | Pixel-perfect paginated reports for federally mandated program submissions, on a fixed statutory calendar | **~** | Entirely out of scope — noted because it's a large, unglamorous, genuinely mandatory part of the real workload. |

### AI tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Inference | Ollama, local, small open-weight models | Azure OpenAI **in Azure Government** (narrower model catalogue, lags commercial by months), or Bedrock in GovCloud | **≈** | Provider swap behind one interface. Output quality differs materially — see §4.8. |
| Embeddings + retrieval | OpenSearch, k-NN plugin, hybrid lexical + vector | Azure AI Search, Elastic, or OpenSearch | **=** | Managed vs. self-hosted; same retrieval concepts. |
| Semantic layer | MetricFlow (open source) | Same, or a vendor semantic layer (Power BI's own model, AtScale) | **=** | Nothing. |
| Document intake | Open-source OCR + a local model | Azure AI Document Intelligence, plus an enterprise content management system (OpenText, FileNet) as the system of record for the document itself | **~** | No ECM here — documents are stored, not *managed* (no retention schedule, no legal hold, no records disposition). |
| Correspondence | Templated generation, rendered to PDF | A customer-communications-management product (Exstream, Quadient, Smart Communications) wired to a print-and-mail vendor, with certified-mail tracking and undeliverable-address handling | **~** | Notices are generated but never *sent*. See §4.4. |
| Evaluation | Golden-question suite scored for groundedness and citation accuracy, gating CI | Same, plus human review panels and periodic model revalidation | **≈** | Scale of the eval set, and who reviews it. |

### Messaging tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Async task queue | **pgmq** (Postgres extension) — decouples document-intake jobs, correspondence dispatch, and fraud-triage triggers from the request/determination path (Phase 3/4) | RabbitMQ or Kafka — a dedicated message broker, deployed and scaled independently of the operational database | **~** | Producer/consumer code swaps from pgmq's SQL functions (`send`/`read`/`delete`) to an AMQP or Kafka client; the enqueue → async-worker pattern carries over, but the broker becomes its own service instead of living inside Postgres. See §4.11. |

### Interfaces tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| External verification | One mock interface (wage/income stand-in): synchronous REST, deterministic canned responses, every request/response an audit-chain event, raw response readable only by an active `CASE_ASSIGNMENT` holder | A dozen-plus real federal and state interfaces — SSA benefit/citizenship verification, IRS income data, DHS immigration-status verification, new-hire and wage databases, interstate duplicate-participation checks | **~** | The mock proves the *pattern* (request, safeguard, audit, reconcile). It cannot prove integration against a real counterparty with a real SLA and a real data-sharing agreement. |
| Transport | REST over HTTPS | Batch SFTP / managed file transfer, message queues, an ESB — often on a nightly cycle, sometimes fixed-width flat files | **~** | Real interfaces are far more batch-oriented and far less RESTful than a modern greenfield design suggests. |

### Platform tier

| Layer | Canopica uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Runtime | Docker Compose, one host | Kubernetes (AKS/OpenShift), multi-node, multi-AZ | **≈** | Container images are unchanged; orchestration manifests are new. |
| IaC | Terraform (reference, not applied by default) | Terraform / Bicep, applied through a gated release pipeline with policy-as-code guardrails | **≈** | Same language, plus approval gates and drift detection. |
| Cloud | Local; documented Azure path | **Azure Government** — separate instance, screened U.S. persons, FedRAMP High / DoD IL4-5 / IRS 1075 / HIPAA accreditation | **~** | Not obtainable without a government or approved-contractor tenant. See the roadmap doc §3.4. |
| Secrets | `.env` + local Keycloak credentials | Key Vault / HashiCorp Vault, HSM-backed, FIPS 140-validated crypto modules, automated rotation | **~** | Substituted for local-run convenience; the *code* reads from an abstraction either way. |
| Observability | OpenTelemetry → Jaeger (traces) + Prometheus/Grafana (metrics), self-hosted single-host containers | OpenTelemetry → Azure Monitor / **Splunk** (near-standard in government), with 24/7 alerting and on-call rotation | **≈** | Backend swap. Instrumentation code is identical — that's the point of OTel. |
| CI/CD | GitHub Actions: build, lint, test, dbt tests, fairness gate, eval gate | Azure DevOps / GitLab, plus SAST, DAST, software composition analysis, container scanning, STIG compliance scanning, and a formal change-approval board | **≈** | More gates, slower cadence, human approval boards. |

## 3. What genuinely transfers

Stripping out everything substituted, these are unchanged between this repo
and a real system, and they are the reason the substitutions are acceptable:

- **The dbt project.** Same models, same tests, same medallion structure.
- **The Delta table format.** Identical bytes on disk.
- **The DMN decision tables.** An open standard, not a private format.
- **The OpenTelemetry instrumentation.** Vendor-neutral by design.
- **The governance model** — effective-dated policy, hash-chained audit,
  caseload-scoped authorization, column-level classification. These are
  design properties, not products, and they don't have a free tier.
- **The Spring Boot / React application code.**
- **The CI gates** — dbt tests, fairness audit, RAG eval. The thresholds
  would change; the mechanism wouldn't.

## 4. Deliberate compromises, and what each one costs

Stated plainly, because an unstated compromise reads as an oversight.

**4.1 Scale.** Thousands of synthetic records, not millions of real ones.
Nothing here proves partitioning strategy, index design, query performance
under concurrency, or archival and purge against a records-retention
schedule. Those are a large fraction of the real engineering effort on a
system this size, and this repo does not demonstrate them.

**4.2 No real external interfaces.** One mock stands in for a dozen real
federal and state data exchanges. The mock proves the safeguarding and
audit *pattern*; it cannot prove integration against a counterparty with a
real SLA, a real data-sharing agreement, and a real outage schedule.

**4.3 No identity proofing.** Keycloak authenticates accounts. It does not
verify that a human is who they claim to be, which is what a real citizen
portal federates to an IAL2 provider to do. Account takeover and synthetic-
identity fraud — significant real threats in benefits programs — are
therefore out of scope.

**4.4 Notices are generated, never sent.** No print-and-mail vendor, no
certified-mail tracking, no undeliverable-address handling, no records
management for the sent artifact. Correspondence is one of those areas
that looks trivial and is not.

**4.5 No high availability, disaster recovery, or operations.** Single-host
Docker Compose. No multi-region failover, no RTO/RPO targets, no tested
recovery drills, no on-call rotation, no runbooks.

**4.6 Controls are demonstrated and self-asserted, not assessed.** The
NIST 800-53 and IRS Pub 1075 mappings show *how* a control would be
implemented and let a reader verify the implementation exists. No
third-party assessment, no Authority to Operate, no penetration test, no
independent Section 508 audit. Self-assertion is not certification, and
this repo does not claim otherwise.

**4.7 No separation of duties.** One person writes the rules, the pipeline,
the security controls, and the tests. Real systems separate development,
database administration, security engineering, release management, and
policy authorship — partly for quality, largely because the compliance
frameworks require it.

**4.8 Local models are materially weaker than frontier models.** The eval
suite's absolute scores are therefore not meaningful as a claim about what
this architecture could achieve; they're meaningful as a *relative*
baseline and as proof that the gate mechanism works and blocks regressions.

**4.9 Fairness auditing runs on synthetic data, which limits what it can
claim.** The applicant records are generated from public census
distributions, which means a disparate-impact measurement over them
partly measures the generator's own assumptions. What the audit
demonstrates is that the measurement, the threshold, and the CI gate all
work and would catch a regression — not that any model here is fair in the
world. Claiming more than that would be exactly the kind of
overstatement the governing principle exists to prevent.

**4.10 No policy subject-matter expert.** Rules are derived from published
federal policy documents by an engineer, not by a caseworker or policy
analyst. Real systems have policy staff who own rule correctness, and the
gap between "what the manual says" and "how it is actually applied" is
where a great deal of real-world complexity lives.

**4.11 Messaging lives inside the operational database, not a dedicated
broker.** pgmq queues share Postgres's resources and failure domain with
the OLTP workload they're decoupling from — a queue backlog can compete
with the operational store it's trying to protect, which defeats part of
the point. There's no independently scaled broker, and none of Kafka's
actual differentiators (durable replay, multiple independent consumer
groups reading the same stream) are available — pgmq gives point-to-point
work queues, not an event log. Real systems isolate the messaging
substrate from the transactional store specifically so the two failure
domains don't collapse into one.

**4.12 Batch ingestion, not CDC.** Bronze fills via a nightly (or
on-demand) full-table extract, not Debezium-style log-based change
capture. At this project's data volume the practical difference is
invisible — a few thousand rows extract in seconds — but a full-table
extract doesn't scale to real write volume without becoming the heaviest,
slowest part of the pipeline, and it can never be more current than the
last run. Debezium (or a managed equivalent) reads the database's
write-ahead log directly and streams each change as it commits: lower
latency and lower load than repeatedly re-querying the whole table, at
the cost of needing a broker to stream into — the same infrastructure
§4.11 already declined to add for messaging. Same substitution, same
reason, documented in the same place.

**4.13 No data catalog.** Lineage and PII classification live in `dbt
docs generate`'s output — genuinely useful, genuinely not a catalog. A
real one (Unity Catalog, Purview, OpenMetadata, DataHub) adds cross-system
lineage (source database through to the Power BI dataset, not just
model-to-model inside one dbt project), automated sensitive-data scanning
instead of a hand-applied `meta` tag, and an access-request workflow. None
of that exists here.

**4.14 One environment, not five.** No dev/sit/uat/prod/sandbox promotion
pipeline — everything runs in a single local Docker Compose stack.
`profiles.yml`'s named targets and the CI workflow's per-push `dbt
build`/`dbt test` run are already shaped to support real promotion; what's
missing is provisioning four more environments to run them against, which
is infrastructure cost a personal project doesn't carry, not a gap in the
pipeline's design.

**4.15 PII tokenization shares a failure domain with the data it
protects.** The `pii_token` vault (Phase 1b) lives in the same Postgres
instance, behind the same database credential, as every other operational
table — not in a separate service with its own credential and key
management the way a real tokenization product or HSM-backed vault would.
Compromising the application database compromises the vault too. This is
the same shape of compromise §4.11 already accepts for `pgmq` — reusing
existing infrastructure instead of standing up a dedicated service —
applied here to PII instead of queues.

## 5. Cost

Running the full stack locally is **$0** and requires no cloud account, no
API key, and no trial credential that can silently expire. The only
recurring cost in the project is the hard-capped hosted-inference budget
for the public demo introduced in Phase 2, which fails closed rather than
overspending.

That constraint drove several choices above — Ollama over a hosted API,
DuckDB over managed Spark, MinIO over cloud storage, Keycloak over a
commercial IdP, pgmq over RabbitMQ/Kafka, batch extraction over
Debezium/CDC, and a `pgcrypto`-backed token vault over a dedicated
tokenization product. In every case the substitute was chosen specifically
because the *interface* it presents matches the production equivalent,
so the migration path is real rather than aspirational.

## 6. Translating prior ETL-tool experience into this stack

Government and enterprise data-warehouse shops disproportionately run
GUI-based ETL tools — Informatica PowerCenter/IICS, IBM DataStage, SSIS —
rather than a modern SQL-first stack, and the "Interfaces tier" and "Data
tier" rows above already name Informatica/DataStage/Ab Initio as the
real-world equivalent of this project's transformation and ingestion
layers, not a hypothetical. What follows is the fuller translation — not
just "what's the dbt equivalent of a Mapping," but the whole shift in how
a warehouse gets built, run, governed, and shipped, because that shift is
the part that actually reads as modernization rather than a tool swap.

### 6.1 Concept mapping, at a glance

| Informatica / DataStage concept | dbt equivalent in this repo | Where |
|---|---|---|
| Source Qualifier / source definition | `sources.yml` declaring the raw operational tables | Bronze layer, roadmap §3.4.2 |
| Staging area (landing raw data before transform) | Bronze — raw, append-only, no reshaping | Roadmap §3.4.2 |
| Mapping / reusable Mapplet | A dbt model / a reusable Jinja macro | `data-platform/models/`, `macros/` |
| Lookup transformation | `ref()` join to a dimension model | Silver-layer `dim_*`/`fct_*` models |
| Expression transformation (derived columns, business rules) | Model SQL (`case when`, computed columns) | Silver/Gold models |
| Aggregator transformation | Model SQL with `group by` | Gold-layer marts |
| Update Strategy / Type 2 slowly-changing dimension | **dbt snapshot** — same concept, built in | `dim_policy_parameter_set`, SCD Type 2 per §3.4.2 |
| Workflow / Session (a scheduled, monitored execution unit) | An Airflow DAG running `dbt run` / `dbt test` | §6.4 below, Phase 1b orchestration |
| Workflow Monitor (run history, row counts, session logs) | Airflow's UI + dbt's own run results | §6.4 below |
| Data-quality rule embedded in a mapping | `not_null`/`unique`/`relationships`/`accepted_values`/freshness dbt tests, enforced in CI | §6.5 below, CLAUDE.md's testing policy |
| Mapping parameter | `dbt_project.yml` vars — or, for business-rule values specifically, Canopica's own effective-dated `policy_parameter_set` pattern | §3.5 |
| Impact analysis before changing a field | `dbt docs generate` / the model DAG — lineage is a first-class artifact, not a side tool | §6.10 below |

### 6.2 The core shift: ETL becomes ELT

Informatica (like DataStage and SSIS) transforms **in flight**: data is
extracted, reshaped inside the tool's own proprietary engine — a Mapping
running on PowerCenter's Integration Service, or a pipeline on IICS's
Secure Agent — and only the already-transformed result is loaded. The
transformation logic lives inside that engine, versioned (if at all)
inside the tool's own repository, and it's largely invisible to anything
outside the tool: no `git diff` on a Mapping, no pull-request review on a
transformation the way a PR reviews SQL.

This project — and the production stack it stands in for, Databricks,
Synapse, or Fabric, all three named in the README's "Cloud target" row and
§3.7 above — inverts that order: **extract and load first, transform
after landing.** Raw data lands as-is in bronze, no reshaping, no business
logic, nothing that can silently drop or mutate a row before anyone can
see what actually arrived — and every transformation from there on is
SQL (plus a thin layer of Jinja for reuse), compiled and run by the
warehouse's own compute engine (DuckDB locally; Spark on
Databricks/Synapse/Fabric in production), and checked into `git` exactly
like application code: reviewable in a diff, testable, revertible by
`git revert` instead of by re-importing an XML export. The
"Transformation" row in §2's Data tier table already states the practical
payoff: *the dbt project is portable as-is* — swapping `dbt-duckdb` for
`dbt-databricks`/`dbt-fabric` is a `profiles.yml` change, not a rewrite,
precisely because none of the transformation logic ever lived inside a
compute-specific proprietary engine to begin with.

### 6.3 Layered modeling: medallion architecture, and one hard rule

§3.4.2 of the roadmap doc lays out the warehouse in three layers — bronze
(raw, append-only, no reshaping), silver (conformed dimensions and facts,
PII classified and tokenized per column), gold (the marts: processing
timeliness, determination outcomes, payment accuracy, fairness audit,
worker caseload, access review). This is the direct descendant of an
Informatica landing-zone/staging-area/mart pattern, made explicit and
enforced rather than left emergent:

**Dashboards and reports query gold, and only gold. Never bronze, never
silver.** Silver still carries un-tokenized joins and intermediate grain
a report has no business seeing directly, and bronze is raw operational
data with no PII classification applied at all — the same reason a
Mapping's staging table was never something a report tool connected to
directly. This isn't a napkin rule here: the serving Postgres database in
§3.4.2 physically receives only gold-layer tables (Task 11's
`materialize.py` writes exactly the `mart_*` tables and nothing upstream
of them), so a report *cannot* reach bronze or silver even by accident —
there's no connection string that resolves to them from the reporting
tier.

### 6.4 Orchestration: from a proprietary scheduler to a dependency-aware DAG

Informatica's Workflow Manager/Monitor (IICS's Taskflows are the same
shape) schedules and runs Sessions largely as a linear, tool-internal
concept: dependency between workflows is expressed as a chain of
scheduled start times or event-wait conditions, retry logic is configured
per-session inside the tool, and failure alerting is whatever email task
you remembered to attach.

Airflow (Phase 1b's Task 4; Azure Data Factory or Fabric Data Factory are
the same shape on Azure — see the Orchestration row in §2's Data tier
table) replaces that with a DAG that is explicit about dependency — a dbt
model's `ref()` graph *is* the dependency graph, no separate scheduling
config has to be kept in sync with it — and gets for free what Informatica
made you configure by hand:

- **Retries** with backoff, per task, without re-running everything
  upstream of a transient failure.
- **SLA alerting** — a task or DAG that hasn't finished by a deadline
  pages someone, instead of a downstream report silently going stale.
- **Backfills** — re-running a specific historical partition/date range
  on demand (SNAP's fiscal-year boundary in §3.5 is exactly the kind of
  thing that needs a clean backfill story), rather than re-running an
  entire Session end to end because the schedule itself has no concept of
  a parameterized date range.
- **Observable run history** — Airflow's UI plus dbt's own
  `run_results.json` stand in for Workflow Monitor's session log, per the
  concept-mapping table in §6.1.

### 6.5 Data quality and observability

Informatica expresses data-quality rules as a transformation embedded in
a Mapping — a Lookup that fails, an Expression that flags a bad row. dbt
expresses the same intent as **tests**, but as declared assertions
instead of imperative logic: `not_null`, `unique`, `relationships`
(referential integrity), `accepted_values`, plus freshness tests (`dbt
source freshness`) that fail a run when a source hasn't landed recently
enough — the direct answer to "is bronze actually current," which a
Mapping never really asserted, it just ran on schedule and hoped.
CLAUDE.md's testing policy already makes this non-negotiable here
specifically: every model gets `not_null`/`unique`/`relationships`/
`accepted_values` tests, plus a custom test asserting no unmasked
PII-shaped column reaches gold — and **CI runs the full dbt test suite on
every pull request that touches a transformation model, before it can
merge**, the same "a red suite blocks the merge" rule CLAUDE.md states for
every other layer, not a special exception carved out for the data
platform.

Tests catch what a row violates; **observability** catches what changed
that no test was written for — a source's row count dropping 40%
overnight, a column's null rate creeping up, a schema drifting out from
under a downstream model without anyone editing a model to cause it. Monte
Carlo and Elementary (an open-source, dbt-native package: it reads dbt's
own artifacts and layers anomaly detection, schema-change alerts, and a
lineage-aware incident view on top) are the named production equivalents
— genuinely not built in this repo, which today has dbt's tests and the
CI gate and nothing watching for an anomaly no one thought to assert. That
gap is worth stating plainly rather than implying the CI gate covers it: a
test catches a known failure mode; an observability tool catches an
unknown one.

**One honest gap on the test side too, not papered over:** dbt has no
native equivalent of Informatica's reject-file/error-row handling — a
failed dbt test flags a run, it doesn't automatically quarantine the
offending rows the way a Mapping's error path did. Closing that for real
(explicit `etl_batch_id`/`_loaded_at` audit columns, row-count
reconciliation between layers, a quarantine table for rows a test
rejects) is a genuine implementation choice for Task 10, not something to
claim exists today — see the `canopica-design-decision` skill if it's picked
up, since it changes the schema design §3.4.2 already specifies.

### 6.6 Incremental loads and CDC, instead of nightly full reloads

The Informatica-shop default this project deliberately breaks from: a
nightly Session that truncates the target and reloads it wholesale,
because building true incremental logic inside a Mapping was enough extra
work that "just reload everything" usually won on cost. Two separate
modernizations replace it, at two different layers:

- **Ingestion (source → bronze):** Change Data Capture — Debezium reading
  the operational database's write-ahead log directly and streaming each
  insert/update/delete as it commits, instead of re-querying the whole
  table on a schedule — is the real-production equivalent named in §2's
  Data tier table's "Ingestion pattern" row. It is **not built here**: it
  requires a broker (Kafka Connect) to stream into, which is exactly the
  infrastructure this project already declined to stand up for messaging
  (§4.11's pgmq substitution) — see §4.12 for what that costs. Phase 1a's
  actual ingestion job (Task 10) is a nightly/on-demand batch extract,
  which at this project's data volume (§4.1) is genuinely
  indistinguishable from CDC in outcome — the honest, stated choice for a
  portfolio project's data volume, since the gap only matters at real
  write throughput.
- **Transformation (silver/gold):** independent of how bronze fills,
  **incremental dbt models** (`materialized='incremental'`, an
  `is_incremental()` guard, a merge/append strategy) cut a model down to
  processing only new/changed rows instead of rebuilding the full table
  every run — the direct dbt equivalent of an Informatica Session
  configured for incremental load rather than truncate-and-reload. Phase
  1a's gold marts are rebuilt wholesale on purpose (stated explicitly in
  Task 11's plan) — genuinely premature at this data volume; incremental
  materialization is called out there as Phase 1b scope, which is also
  where CDC-fed bronze would land if it were ever built.

### 6.7 One semantic layer, not one metric definition per dashboard

Two rows already in this doc are actually one layer, described from two
angles: "Semantic layer: MetricFlow" (§2, AI tier — governs what the
Analytics Copilot is allowed to compute) and "Semantic model: TMDL" (§2,
Reporting tier — governs what Power BI renders). The point of a semantic
layer, in an Informatica shop's usual absence of one, is that "net
income" or "processing time" gets defined **once**, with one formula, one
set of filters, one name — instead of the same metric quietly getting
re-derived (and, over enough reports, quietly drifting) inside a Business
Objects universe here, a Tableau calculated field there, and a raw SQL
aggregator in a Mapping somewhere else. MetricFlow is that definition for
anything the AI layer or a governed BI query touches; the TMDL model is
the same discipline applied to Power BI specifically, and Power BI's
**XMLA endpoint** (a live-query connection into a published dataset,
available on Premium/Fabric capacity) is what would let *every* Power BI
report — not just the ones in this repo's own `reporting/` folder —
connect to that one governed model instead of importing its own copy of
the data and its own copy of the logic. Genuinely not exercised here: the
free Power BI Service tier this project runs on doesn't carry XMLA
read/write, so "one governed model, many reports" is correct as *design*,
not yet demonstrated as a live connection — the same class of honest gap
the "Interactive reports" row above already states for RLS and refresh
scheduling.

### 6.8 Security enforced at the warehouse/semantic layer, not per report

The same "define once" principle applies to row- and column-level
security. Column-level: PII tokenization happens once, in silver
(§3.4.2: "cleaned, conformed, PII classified and tokenized per column"),
so every gold mart and every report built on it inherits the masking
automatically — nobody re-implements a mask inside a report's own query.
Row-level: the Authorization row above (Spring Security RBAC plus
caseload-scoped row filtering) is the operational-tier version of the
same idea, and the reporting-tier production equivalent is a Power BI RLS
role defined once inside the semantic model — a DAX filter expression
tied to the viewer's identity, evaluated by the model itself before any
visual renders — rather than every report author hand-writing a `WHERE
worker_id = ...` filter and hoping every report remembers to. That RLS
role is designed into the TMDL model's target shape but, same honest gap
as §6.7, isn't enforced end-to-end today: enforcing it needs the
Premium/Fabric capacity this project doesn't run.

### 6.9 Centralized secrets and configuration

An Informatica connection object (a database DSN, a set of credentials)
is typically stored inside the repository/domain itself — reusable across
Mappings, but still a config artifact living in the ETL tool's own
metadata, not in a secrets manager built for the purpose. This project's
Secrets row above (`.env` locally; Key Vault/Vault, HSM-backed, in
production) already states the intended target; worth being explicit here
that it's the same convention on every tier that needs a credential — the
portal's Spring config, the data platform's `Settings`
(`canopica_data.config`), Airflow's connection store once Phase 1b builds it,
and Metabase's provisioning script — rather than each one inventing its
own place to keep a password, which is exactly the sprawl a real
Informatica shop's per-connection-object model tends toward at scale.

### 6.10 A data catalog for lineage and PII classification

`dbt docs generate` produces a real, useful artifact — a model-level DAG,
column descriptions, and (via dbt's `meta` tags) a place to mark which
columns are PII — and it's what this repo actually has today. It is not a
data catalog. A real one — Unity Catalog on Databricks, Microsoft Purview
on Azure/Fabric, or an open-source alternative like OpenMetadata or
DataHub — adds three things dbt's own docs site doesn't: lineage that
crosses *system* boundaries (source database → bronze → silver → gold →
Power BI dataset, not just model-to-model inside one dbt project),
automated PII/sensitive-data scanning rather than a manually-applied
`meta` tag, and an access-request/approval workflow tied to a column's
classification. Genuinely not built here — see §4.13.

### 6.11 CI/CD environment separation, and automated deployment

Canopica today runs in exactly one environment: local Docker Compose. A real
program runs five, promoted by pipeline rather than by hand: **dev** (an
individual engineer's own sandbox for a change in progress), **sit**
(system integration testing — do the pieces actually work together),
**uat** (user acceptance — policy/business staff sign off before
production), **prod**, and a separate ad hoc **sandbox** for one-off
analysis that shouldn't touch any of the four promotion-gated tiers at
all. Informatica's version of this is folder-based promotion inside the
repository (a deployment group copying objects from a DEV folder to a
TEST folder to a PROD folder) plus a change-approval step at each
boundary; the dbt/Power BI equivalent is:

- **dbt**: named targets in `profiles.yml` (`dev`/`sit`/`uat`/`prod`),
  each pointing at its own warehouse/serving database, with `dbt build`
  run against the target matching the pipeline stage — the CI workflow
  already runs `dbt build`/`dbt test` on every push (§6.5); the only
  thing missing to make this real is provisioning four more environments
  to run it against, which is infrastructure spend, not new pipeline
  code.
- **Power BI**: Deployment Pipelines (or, on capacity without that
  feature, a scripted call to the Power BI REST API's dataset-refresh
  endpoint) moves the published dataset dev → test → prod in lockstep
  with the dbt release it depends on, instead of a report author manually
  re-pointing a `.pbix` at a different database per environment.

None of this is built — see §4.14 — but it's worth being explicit that
the *reason* it isn't is provisioning cost for a personal project, not a
gap in how the pipeline is structured: the CI workflow and `profiles.yml`
targets are already shaped to support it.
