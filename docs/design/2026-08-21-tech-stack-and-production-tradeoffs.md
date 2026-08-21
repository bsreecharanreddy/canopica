# IES — Tech Stack, Production Equivalents, and Deliberate Trade-offs

Status: approved
Date: 2026-08-21

## 1. Why this document exists

Every technology choice in IES is one of three things:

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

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| API | Spring Boot (Java) | Spring Boot / Jakarta EE on an app server; .NET in some shops | **=** | Nothing. Same framework, same patterns. |
| Web UI | React (one app, role-gated views) | React or Angular, usually **two separate applications** — a public-internet citizen portal and an intranet worker portal, with different threat models and release cadences | **≈** | Split into two builds; citizen app behind WAF/CDN, worker app network-restricted. |
| API edge | Direct to service | API gateway (Azure APIM, Apigee), WAF, rate limiting, mutual TLS between tiers | **~** | Insert gateway; no application code change. |
| Identity — authentication | Keycloak, self-hosted OIDC, two realms | PingFederate / ForgeRock / Entra External ID for citizens; enterprise SSO (SAML/OIDC) + PIV/CAC for staff | **≈** | Swap the OIDC provider. Spring Security config changes; application code does not. |
| Identity — *proofing* | None | **This is the real gap.** Citizen portals federate to a NIST IAL2 identity-proofing service (Login.gov, ID.me) that verifies a human is who they claim before an account exists | **~** | Genuinely absent here — see §4.3. Keycloak authenticates an account; it does not prove an identity. |
| Authorization | Spring Security RBAC + caseload-scoped row filtering | Same, plus attribute-based policies, sensitive-case sealing (VIP/employee/domestic-violence cases), and periodic access recertification | **≈** | Add recertification workflow; core model is the same. |

### Rules tier

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Rules engine | DMN 1.x decision tables, evaluated by an embedded open-source DMN engine | Commercial policy-automation suites (Oracle Policy Automation, IBM ODM, Red Hat Decision Manager, FICO Blaze) | **≈** | DMN is an OMG standard several of those products implement. Rules stay authored as data, not code, either way — that property is what transfers, not the vendor. |
| Rule authoring | Decision tables in the repo, reviewed via pull request | A policy-analyst-facing authoring GUI, with a separate approval workflow and a rules release cycle decoupled from application releases | **~** | No GUI here. PR review stands in for the approval workflow — the governance concept survives, the tooling doesn't. |
| Policy versioning | Effective-dated parameter sets, version stamped on every determination | Same — mandatory, because federal thresholds change annually and determinations must be reproducible as-of their decision date | **=** | Nothing. This is not a place to compromise; see the roadmap doc. |

### Data tier

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Operational store | Postgres | Oracle (still dominant in legacy state systems), SQL Server, or Postgres | **≈** | Dialect differences in DDL only. |
| Transformation | dbt, medallion (bronze/silver/gold) | dbt on Databricks/Snowflake/Fabric — or, in older systems, Informatica / DataStage / Ab Initio | **=** | The dbt project is portable as-is. |
| Compute engine | DuckDB (local, in-process) | Spark on Databricks, Fabric, or Synapse | **≈** | A dbt profile swap (`dbt-duckdb` → `dbt-databricks`). Model SQL is unchanged. |
| Table format | Delta Lake, via the open-source `deltalake` library (no Spark) | Delta Lake on Databricks/Fabric, or Iceberg | **=** | Same on-disk format, byte for byte. |
| Object storage | MinIO (S3-compatible) | ADLS Gen2 / S3, with lifecycle policies, immutability holds, and CMK encryption | **≈** | Endpoint + credential change; lifecycle/retention policies added. |
| Serving layer | Postgres, materialized gold | Fabric Warehouse, Synapse Dedicated SQL Pool, Azure SQL MI, Exadata | **≈** | Connection change; partitioning and distribution keys become real work at volume. |
| Orchestration | Airflow (Docker Compose) | Airflow (managed), Azure Data Factory, Fabric Data Factory — or **Control-M / AutoSys**, which remain very common in government | **≈** | DAG concepts transfer; scheduler product does not. |
| Data volume | Thousands of synthetic records | Millions of persons, tens of millions of benefit-month rows, decades of retained history | **~** | See §4.1 — this is the single largest fidelity gap in the data tier. |

### Reporting tier

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Semantic model | Model-as-code (TMDL), version-controlled | Same model, hosted on Fabric/Power BI Premium capacity | **=** | Deploy target only. |
| Interactive reports | Power BI (free tier / Service) + a containerized OSS dashboard so the repo renders for anyone who clones it | Power BI Premium capacity with row-level security, gateways, deployment pipelines, and workspace governance | **≈** | RLS enforcement, refresh scheduling, and capacity management are all absent here. |
| Regulatory reports | Not built | Pixel-perfect paginated reports for federally mandated program submissions, on a fixed statutory calendar | **~** | Entirely out of scope — noted because it's a large, unglamorous, genuinely mandatory part of the real workload. |

### AI tier

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Inference | Ollama, local, small open-weight models | Azure OpenAI **in Azure Government** (narrower model catalogue, lags commercial by months), or Bedrock in GovCloud | **≈** | Provider swap behind one interface. Output quality differs materially — see §4.8. |
| Embeddings + retrieval | OpenSearch, k-NN plugin, hybrid lexical + vector | Azure AI Search, Elastic, or OpenSearch | **=** | Managed vs. self-hosted; same retrieval concepts. |
| Semantic layer | MetricFlow (open source) | Same, or a vendor semantic layer (Power BI's own model, AtScale) | **=** | Nothing. |
| Document intake | Open-source OCR + a local model | Azure AI Document Intelligence, plus an enterprise content management system (OpenText, FileNet) as the system of record for the document itself | **~** | No ECM here — documents are stored, not *managed* (no retention schedule, no legal hold, no records disposition). |
| Correspondence | Templated generation, rendered to PDF | A customer-communications-management product (Exstream, Quadient, Smart Communications) wired to a print-and-mail vendor, with certified-mail tracking and undeliverable-address handling | **~** | Notices are generated but never *sent*. See §4.4. |
| Evaluation | Golden-question suite scored for groundedness and citation accuracy, gating CI | Same, plus human review panels and periodic model revalidation | **≈** | Scale of the eval set, and who reviews it. |

### Interfaces tier

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| External verification | One mock interface (wage/income stand-in) with FTI-style safeguards genuinely applied | A dozen-plus real federal and state interfaces — SSA benefit/citizenship verification, IRS income data, DHS immigration-status verification, new-hire and wage databases, interstate duplicate-participation checks | **~** | The mock proves the *pattern* (request, safeguard, audit, reconcile). It cannot prove integration against a real counterparty with a real SLA and a real data-sharing agreement. |
| Transport | REST over HTTPS | Batch SFTP / managed file transfer, message queues, an ESB — often on a nightly cycle, sometimes fixed-width flat files | **~** | Real interfaces are far more batch-oriented and far less RESTful than a modern greenfield design suggests. |

### Platform tier

| Layer | IES uses | Real production equivalent | Fidelity | What would change |
|---|---|---|---|---|
| Runtime | Docker Compose, one host | Kubernetes (AKS/OpenShift), multi-node, multi-AZ | **≈** | Container images are unchanged; orchestration manifests are new. |
| IaC | Terraform (reference, not applied by default) | Terraform / Bicep, applied through a gated release pipeline with policy-as-code guardrails | **≈** | Same language, plus approval gates and drift detection. |
| Cloud | Local; documented Azure path | **Azure Government** — separate instance, screened U.S. persons, FedRAMP High / DoD IL4-5 / IRS 1075 / HIPAA accreditation | **~** | Not obtainable without a government or approved-contractor tenant. See the roadmap doc §3.4. |
| Secrets | `.env` + local Keycloak credentials | Key Vault / HashiCorp Vault, HSM-backed, FIPS 140-validated crypto modules, automated rotation | **~** | Substituted for local-run convenience; the *code* reads from an abstraction either way. |
| Observability | OpenTelemetry → local collector | OpenTelemetry → Azure Monitor / **Splunk** (near-standard in government), with 24/7 alerting and on-call rotation | **≈** | Backend swap. Instrumentation code is identical — that's the point of OTel. |
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

## 5. Cost

Running the full stack locally is **$0** and requires no cloud account, no
API key, and no trial credential that can silently expire. The only
recurring cost in the project is the hard-capped hosted-inference budget
for the public demo introduced in Phase 2, which fails closed rather than
overspending.

That constraint drove several choices above — Ollama over a hosted API,
DuckDB over managed Spark, MinIO over cloud storage, Keycloak over a
commercial IdP. In every case the substitute was chosen specifically
because the *interface* it presents matches the production equivalent,
so the migration path is real rather than aspirational.
