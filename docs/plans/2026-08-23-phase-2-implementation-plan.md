# Phase 2 — Policy Intelligence & Analytics AI: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> Execute tasks in order, one commit per completed task, `docs/STATUS.md`
> updated in that same commit (CLAUDE.md, "Conventions"). Run the
> `canopica-task-checkpoint` skill's gate (`make test`, `make lint`, STATUS.md,
> one commit, push) after every task.

**Goal:** Stand up Phase 2's AI capability layer on top of the Phase 1
system of record: a real OpenSearch policy corpus, Policy Q&A/
explainability RAG, a rule-authoring copilot, a MetricFlow-backed
Analytics Copilot, dashboard-authoring assist, an eval-suite CI gate, and
the public hosted demo — with every AI output staying on the "drafts,
flags, explains" side of the governing principle.

**Spec:** `docs/design/2026-08-21-full-system-and-phased-roadmap.md` §3.2/
§3.3/§5 (what), `docs/design/2026-08-23-phase-2-policy-intelligence-
analytics-ai-design.md` (how — read this one first, it resolves every open
question this plan assumes as settled), `docs/design/2026-08-21-tech-
stack-and-production-tradeoffs.md` (fidelity/cost rationale for every
substitution below).

**Starting point, worth internalizing before Task 1:** Phase 2 starts from
a clean slate on the AI side — no `ai/` directory exists yet, no
OpenSearch or Ollama service is in `infra/docker-compose.yml`, no
MetricFlow semantic model exists anywhere in the repo, and (a real gap
this plan found while writing it, not asserted from the design doc) there
is currently **no citizen-facing endpoint at all** — only
`POST /api/applications` is citizen-authenticated; every other endpoint
(`WorkerCaseController`, `SupervisorController`, `DeterminationController`)
is worker/supervisor-only, and `person`/`household` have no Keycloak
subject linkage the way `worker.keycloak_subject` does. The "why was I
denied" entry point (design doc §2.2) needs a citizen to read their own
determination trace, so Task 2 below has to build that linkage — it is
not pre-existing scaffolding the way Phase 1b's `case_assignment`/
`verification` tables were.

Five things this plan settles that the design doc deliberately left open
(§4, "what this doc does not settle") — recorded here once, not
re-derived per task:

- **New Python project**: `ai/` is a second `uv`-managed project
  (`ai/pyproject.toml`, package `canopica_ai`), sibling to `data-platform/`, not
  three separate projects under `ai/policy-intelligence/` etc. — one
  `ruff`/`mypy --strict`/`pytest` surface to wire into `make test`/
  `make lint`, matching this repo's existing one-Python-project-per-
  concern pattern. The roadmap §6 directory names
  (`policy-intelligence/`, `analytics-copilot/`, `dashboard-assist/`)
  become importable packages (`canopica_ai.policy_intelligence`,
  `canopica_ai.analytics_copilot`, `canopica_ai.dashboard_assist`) under one
  `ai/src/` tree, not top-level directories with their own tooling.
- **OpenSearch version**: `opensearchproject/opensearch:2.19.x` — the
  first GA release with the `rrf` combination technique in the hybrid
  search pipeline's normalization processor (design doc §2.1's fusion
  requirement). Exact patch pinned at implementation time, same treatment
  already given to every other image tag in this repo.
- **Reranker mechanism**: an OpenSearch ml-commons local cross-encoder
  model behind a `rerank` response processor — not app-side reranking —
  because the design doc is explicit that this is "a pipeline
  configuration choice against infrastructure already chosen, not a new
  system to stand up" (§2.1). Exact model tag (a small cross-encoder,
  e.g. an ONNX-exported `ms-marco-MiniLM`-family model) pinned at
  implementation time, mirroring the Ollama-tag deferral already in the
  design doc (§2.9).
- **Rule-authoring copilot's persistence split**: the Python AI service
  only computes a proposal and returns it as a validated Pydantic
  response — it never writes to Postgres. The API (Java) persists the
  proposal, records the review decision, and — only on accept — publishes
  through `PolicyParameterSetRepository`/`PolicyParameterRepository`'s
  existing `save()` (inherently insert-only; the `V3` immutability
  trigger blocks `UPDATE`/`DELETE`). This keeps "AI drafts, deterministic
  system decides" a structural property, not a convention the AI service
  has to honor voluntarily.
- **Public demo hosting**: **Fly.io** — Docker-native (deploys the same
  images this repo already builds), persistent volumes for OpenSearch's
  index data. The concrete pick the design doc's §2.7 left open. **Not a
  free tier** (corrected 2026-08-26, live-checked at Task 9
  implementation time): Fly.io removed free-tier signups in October
  2024; realistic all-in cost for the smallest always-on machine plus a
  small volume is ~$5/mo. Render was the other option §2.7 named and is
  ruled out on a hard constraint, not cost — its free web services have
  no persistent disk, which the OpenSearch volume below needs. Vercel was
  considered when this cost was reassessed and ruled out on an even
  harder constraint: its serverless functions support no persistent
  process and no arbitrary TCP ports, so an always-resident OpenSearch
  process cannot run there on any plan, free or paid.

---

## Global constraints

Everything Phase 1a's and Phase 1b's plans stated still applies (never
name a real agency; full suite before every push; one commit per task
with `docs/STATUS.md` in the same commit; synthetic data only;
local-first, $0 by default). Phase 2 adds:

12. **AI never makes a binding decision.** Every task below produces a
    draft, an explanation, or a read-only query result — never a value
    written into `eligibility_determination`, `policy_parameter_set`, or
    any other binding table without an explicit human accept step. If a
    task's own design would have an LLM output land in a binding table
    directly, that is a design bug, not an implementation shortcut — stop
    and revise the task, don't implement around it.
13. **Structured output, not free text, at every AI→system boundary**
    (design doc §2.10). Every LLM response that becomes another
    component's input — a parameter-set diff, an MCP tool-call's
    arguments, a dashboard spec — is Pydantic-v2-validated before it's
    rendered as a diff or executed. A response that fails validation is a
    rejected draft, logged as such, never partially applied.
14. **Ollama is the default runtime everywhere except the public demo.**
    Every task's local/CI path calls the self-hosted Ollama models
    already named as this project's cross-cutting AI-runtime default
    (roadmap §3.3); only Task 9's public deployment switches to the
    OpenRouter tiered fallback, behind the same client interface Task 2
    establishes.
15. **Every substitution this phase makes gets a tradeoffs-doc row or
    tightened existing row**, per the `canopica-design-decision` skill —
    Phase 2's design doc already added the "Embeddings + retrieval" and
    "Public-demo inference" rows; a task that makes a new substitution
    (e.g. the reranker mechanism, the eval-gate tooling) records it the
    same way if it isn't already covered.

### New dependencies this phase

| Component | Choice | Why |
|---|---|---|
| Vector + lexical search | OpenSearch 2.19.x (`opensearchproject/opensearch`) | Design doc §2.1; roadmap §3.3 |
| AI runtime, local/default | Ollama (`ollama/ollama`), one generation + one embedding model tag, pinned at implementation time | Roadmap §3.3; design doc §2.9 |
| Reranker | OpenSearch ml-commons local cross-encoder model + `rerank` response processor | Design doc §2.1 |
| MCP | `mcp` (official Python SDK) | Design doc §2.4; roadmap §3.3 |
| MetricFlow | `dbt-metricflow` (dbt Labs OSS package) | Design doc §2.4; roadmap §3.3 |
| RAG eval | `ragas`, `deepeval` | Design doc §2.6; roadmap §3.3 |
| AI service framework | FastAPI (matches this project's Python-first, current-tooling convention) | CLAUDE.md language policy |
| Public demo inference | OpenRouter (`:free`-tagged models, capped paid fallback) | Design doc §2.7 |
| Public demo hosting | Fly.io | This plan's own concrete pick, above |
| AI observability | `opentelemetry-sdk`/`opentelemetry-exporter-otlp` (already a `data-platform` dependency; added to `ai/` too) | Design doc §2.8 |

### Prerequisites before Task 1

- [x] Docker Desktop running (`docker info` succeeds) — OpenSearch and
      Ollama both add new containers to `infra/docker-compose.yml`;
      OpenSearch in particular wants real memory headroom (`vm.max_map_count`
      may need raising on the host, standard OpenSearch requirement — check
      and document in `infra/README` or the compose file's own comment if
      so). Verified: this host's Docker Desktop VM already reports
      `vm.max_map_count=262144` (the exact minimum), documented in
      `infra/docker-compose.yml`'s own comment for a host that doesn't.
- [ ] An OpenRouter account exists and its API key is available for
      `.env` (used only by Task 9's public-demo path; every earlier task
      runs entirely against local Ollama and needs no external account).
- [ ] A Fly.io account exists (needed only at Task 9).

---

## File structure (additions only)

```
canopica/
  ai/
    pyproject.toml                          <- Task 1
    uv.lock                                 <- Task 1
    src/canopica_ai/
      __init__.py
      config.py                             <- Task 1 (Settings, pydantic-settings)
      common/
        observability.py                    <- Task 8
        llm_client.py                       <- Task 2, extended Task 9
        guardrails.py                       <- Task 9
      policy_intelligence/
        corpus/
          cfr_fetch.py                      <- Task 1
          chunk.py                          <- Task 1
          index.py                          <- Task 1
          search_pipeline.py                <- Task 1
        retrieval.py                        <- Task 1
        qa/
          service.py                        <- Task 2
          grounding.py                      <- Task 2
          provenance.py                     <- Task 2
          api.py                            <- Task 2
        rule_authoring/
          service.py                        <- Task 3
          schema.py                         <- Task 3
          api.py                            <- Task 3
        eval/
          golden_set.yaml                   <- Task 7
          run_eval.py                       <- Task 7
          baseline.json                     <- Task 7
      analytics_copilot/
        mcp_server.py                       <- Task 5
        tools.py                            <- Task 5
        service.py                          <- Task 5
      dashboard_assist/
        cli.py                              <- Task 6
        service.py                          <- Task 6
      public_demo/
        app.py                              <- Task 9
        static/index.html                   <- Task 9
        rate_limit.py                       <- Task 9
    tests/
      conftest.py                           <- Task 1
      test_corpus_index.py                  <- Task 1
      test_retrieval.py                     <- Task 1
      test_policy_qa.py                     <- Task 2
      test_citizen_determination_access.py  <- Task 2 (Java-side, see below)
      test_rule_authoring.py                <- Task 3
      test_metric_semantics.py              <- Task 4
      test_analytics_copilot.py             <- Task 5
      test_dashboard_assist.py              <- Task 6
      test_eval_gate.py                     <- Task 7
      test_ai_observability.py              <- Task 8
      test_public_demo.py                   <- Task 9
  api/src/main/resources/db/migration/
    V12__person_keycloak_identity.sql       <- Task 2
    V13__policy_parameter_proposal.sql      <- Task 3
  api/src/main/java/canopica/api/
    api/CitizenController.java              <- Task 2
    config/KeycloakCitizenLinkFilter.java   <- Task 2
    policy/PolicyParameterPublishService.java <- Task 3
    api/PolicyParameterProposalController.java <- Task 3
  ui/src/
    pages/PolicyQaPage.tsx                  <- Task 2
    pages/RuleAuthoringPage.tsx             <- Task 3
  data-platform/dbt/canopica_warehouse/models/semantic/
    semantic_models.yml                     <- Task 4
    metrics.yml                             <- Task 4
  infra/
    docker-compose.yml                      <- modified: +opensearch, +ollama, Task 1
    postgres/init/01-databases.sql          <- modified: +canopica_analytics_ro, Task 4
    opensearch/
      cfr_index_mapping.json                <- Task 1
      search_pipeline.json                  <- Task 1
    fly/
      fly.toml                              <- Task 9
      Dockerfile.public-demo                <- Task 9
  reporting/semantic-model/proposals/       <- Task 6 (LLM-proposed TMDL diffs land here)
  .github/workflows/ci.yml                  <- modified: +ai job, +ai-eval job
  Makefile                                  <- modified: ai lint/test targets folded into `make test`/`make lint`
```

---

## Task list

| # | Task | Deliverable |
|---|---|---|
| 1 | OpenSearch corpus & hybrid retrieval | CFR corpus indexed; hybrid (BM25+k-NN) query with RRF fusion + reranking returns real, ranked chunks |
| 2 | Policy Q&A / explainability RAG | Both entry points answer grounded, cited questions with a persisted provenance record; citizen can view their own denial explanation |
| 3 | Rule-authoring copilot | LLM proposes a `policy_parameter_set` diff; worker reviews and publishes through the existing insert-only path |
| 4 | MetricFlow semantic layer | `semantic_models:`/`metrics:` YAML over all 5 gold marts; `mf query` runs locally; `canopica_analytics_ro` role live |
| 5 | Analytics Copilot | NL question → MCP tool call → MetricFlow query → result + compiled SQL, authorized by caller role before compile |
| 6 | Dashboard-authoring assist | CLI proposes a TMDL diff + DAX measures as a reviewable patch file, never auto-applied |
| 7 | Eval-suite CI gate | RAGAS/DeepEval + deterministic citation pre-check, baseline-relative thresholds, blocking in CI |
| 8 | AI observability | `gen_ai.*` spans in Jaeger for every LLM/retrieval call; `rag_citation_grounded` attribute live per request |
| 9 | Public hosted demo | Policy Q&A reachable at a public Fly.io URL, tiered OpenRouter fallback, guardrails, rate-limited |

---

## Task 1: OpenSearch corpus & hybrid retrieval

Stands up the `ai/` project itself, the OpenSearch + Ollama infrastructure,
ingests the real 7 CFR Part 273 sections this project's rules engine
implements, and builds the hybrid-retrieval query path (RRF fusion +
reranking) that every later AI feature reads from. No generation yet —
this task proves retrieval alone returns the right chunks.

**Files:**
- Create: `ai/pyproject.toml`, `ai/uv.lock`
- Create: `ai/src/canopica_ai/__init__.py`, `ai/src/canopica_ai/config.py`
- Create: `ai/src/canopica_ai/policy_intelligence/corpus/cfr_fetch.py`,
  `chunk.py`, `index.py`, `search_pipeline.py`
- Create: `ai/src/canopica_ai/policy_intelligence/retrieval.py`
- Create: `ai/tests/conftest.py`, `test_corpus_index.py`,
  `test_retrieval.py`
- Create: `infra/opensearch/cfr_index_mapping.json`,
  `infra/opensearch/search_pipeline.json`
- Modify: `infra/docker-compose.yml` (+`opensearch`, +`ollama`)
- Modify: `Makefile` (`test`/`lint` include `ai/`), `.github/workflows/ci.yml`
  (+`ai` job running `ai/`'s ruff/mypy/pytest)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.policy_intelligence.retrieval.hybrid_search(query: str,
  top_k: int = 5) -> list[RetrievedChunk]`, where `RetrievedChunk` (Pydantic)
  carries `cfr_section: str`, `heading: str`, `text: str`, `chunk_id: str`,
  `score: float`. This is the sole read interface Task 2's Q&A service, and
  Task 7's eval harness, call — neither talks to OpenSearch directly.
- Consumes: Ollama's `/api/embeddings` endpoint (via `httpx`, already
  proven in `data-platform`'s dependency set) for both indexing-time and
  query-time embeddings.

```json
// infra/opensearch/cfr_index_mapping.json (shape, not final)
{
  "settings": { "index.knn": true },
  "mappings": {
    "properties": {
      "cfr_section": { "type": "keyword" },
      "heading": { "type": "text" },
      "text": { "type": "text" },
      "embedding": { "type": "knn_vector", "dimension": 768 }
    }
  }
}
```

- [x] **Step 1: `ai/` project scaffold.** `uv init` at `ai/`, package
      `canopica_ai`; `pyproject.toml` mirrors `data-platform/pyproject.toml`'s
      `[tool.ruff]`/`[tool.mypy]` blocks (`strict = true`, `target py312`)
      so both projects hold the same bar. Add to `Makefile`'s `test`/`lint`
      targets and a new `ai` job in `ci.yml` (same shape as the existing
      `dbt`/Python job).
- [x] **Step 2: Compose services.** `opensearch` (single-node,
      `discovery.type=single-node`, security plugin disabled for local
      dev — same "no TLS locally" posture the compliance-mapping doc
      already states as a known gap for `postgres`) and `ollama`
      (`ollama/ollama`, a named volume for pulled models, an init
      container or `docker compose run --rm ollama ollama pull <tag>`
      documented in `infra/README`/`Makefile` for pulling the pinned
      generation + embedding models on first `make up`).
- [x] **Step 3: CFR ingestion.** `cfr_fetch.py` pulls the real text for
      the sections design doc §2.1 scopes (gross/net income tests, the
      standard/earned-income/dependent-care/medical/shelter deductions,
      categorical eligibility, expedited processing/273.2(i)) from eCFR's
      public API, caching the raw fetched text under
      `ai/src/canopica_ai/policy_intelligence/corpus/raw/` (committed — a
      portfolio project's corpus should be reproducible without a live
      network call on every `make up`). `chunk.py` splits at CFR
      subsection boundaries (e.g. `273.9(c)(1)`), producing one document
      per subsection with `cfr_section`/`heading`/`text`.
- [x] **Step 4: Index + embed.** `index.py`'s CLI
      (`uv run python -m canopica_ai.policy_intelligence.corpus.index`)
      creates the OpenSearch index from `cfr_index_mapping.json`,
      embeds each chunk's `text` via Ollama, and bulk-indexes. Idempotent
      — re-running against an already-indexed corpus is a no-op diff, not
      a duplicate-append (delete-and-recreate the index each run, since
      corpus size is small and this only runs at ingestion time, not per
      request).
- [x] **Step 5: Search pipeline.** `search_pipeline.json` defines an
      OpenSearch search pipeline: a `normalization-processor` with
      `technique: rrf` combining the BM25 and k-NN sub-queries, followed
      by a `rerank` response processor referencing the ml-commons
      cross-encoder model (registered via `search_pipeline.py`'s own
      one-time setup call — model group creation, local model
      registration/deployment, pipeline creation, all idempotent/
      check-before-create). Document the exact model tag chosen at
      implementation time in this file's own comment, same as every
      other pinned-at-implementation-time value in this repo.
- [x] **Step 6: `hybrid_search()`.** `retrieval.py` issues one hybrid
      query (BM25 sub-query + k-NN sub-query over the query's own
      embedding) through the pipeline from Step 5, returns the top-k
      reranked chunks as `RetrievedChunk` Pydantic models.
- [x] **Step 7: Tests.** `test_corpus_index.py`: the index exists, has
      the expected document count, and a known CFR section's exact text
      round-trips. `test_retrieval.py`: a query about the gross income
      test returns `273.9`-family sections in the top few results before
      reranking changes ordering; confirm reranking actually changes
      result order on at least one query pair (proves the pipeline step
      is live, not a no-op).
- [x] **Step 8: Full suite + commit.**

---

## Task 2: Policy Q&A / explainability RAG

Both entry points from design doc §2.2, sharing Task 1's retrieval core.
"Why was I denied" needs a citizen to read their own determination trace
— a capability that does not exist anywhere in the API yet (see this
plan's opening note) — so this task also closes that gap.

**Files:**
- Create: `ai/src/canopica_ai/policy_intelligence/qa/service.py`, `grounding.py`,
  `provenance.py`, `api.py`
- Create: `ai/src/canopica_ai/common/llm_client.py` — `LlmClient` protocol +
  `OllamaClient`, the only implementation until Task 9 adds
  `OpenRouterTieredClient` behind the same interface
- Create: `ai/tests/test_policy_qa.py`
- Create: `api/src/main/resources/db/migration/
  V12__person_keycloak_identity.sql`
- Create: `api/src/main/java/canopica/api/api/CitizenController.java`,
  `api/src/main/java/canopica/api/config/KeycloakCitizenLinkFilter.java`
- Create: `api/src/test/java/canopica/api/api/
  CitizenDeterminationAccessTest.java`
- Create: `ui/src/pages/PolicyQaPage.tsx`
- Modify: `api/src/main/java/canopica/api/config/SecurityConfig.java`
  (new citizen-scoped `GET` routes)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: `canopica_ai.policy_intelligence.retrieval.hybrid_search()` (Task
  1); a new API endpoint `GET /api/my/determinations/{id}/trace`
  (this task) for the "why was I denied" path.
- Produces: `canopica_ai.policy_intelligence.qa.service.answer_general(question:
  str) -> QaAnswer` and `answer_denial(determination_id: UUID, jwt_sub: str)
  -> QaAnswer`, where `QaAnswer` (Pydantic) carries `answer: str`,
  `citations: list[str]` (CFR sections), `abstained: bool`, plus every
  field `provenance.py` records (below). Task 7's eval harness and Task 9's
  public-demo app both call `answer_general` directly — the sole entry
  point for the general-question path.

```sql
-- V12__person_keycloak_identity.sql
alter table person add column keycloak_subject text unique;
-- Populated at intake time: IntakeController already receives a citizen-
-- realm JWT for POST /api/applications (SecurityConfig's citizenFilterChain);
-- this task reads its `sub` claim and stamps it onto the person row(s)
-- created for that submission, the same "provision on first real use"
-- shape KeycloakWorkerSyncFilter already established for workers.
```

- [x] **Step 1: Link citizens to their own data.** `V12` migration adds
      `person.keycloak_subject`. `IntakeController`'s existing handler
      (already behind `citizenFilterChain`, already has the JWT via
      `Authentication`) sets it on the submitting person when creating
      the `person`/`household` rows — a one-line addition at an existing
      write path, not a new provisioning filter (unlike
      `KeycloakWorkerSyncFilter`, there's no "first login creates the
      row" case here; the row is always created at submission time).
- [x] **Step 2: `CitizenController` + `KeycloakCitizenLinkFilter`.** New
      `GET /api/my/program-requests` (lists the caller's own, resolved by
      `keycloak_subject`) and `GET /api/my/determinations/{id}/trace`
      (same shape as `WorkerCaseController`'s existing trace endpoint,
      but scoped: 403 unless the determination's household traces back to
      a person whose `keycloak_subject` matches the caller's JWT `sub` —
      ownership, not caseload assignment). `KeycloakCitizenLinkFilter`
      resolves `Authentication#getName()` (the JWT `sub`) to a `person_id`
      once per request, mirroring the read pattern
      `KeycloakWorkerSyncFilter` already established for the write case.
- [x] **Step 3: `SecurityConfig` route additions.** Both new `GET` routes
      added to `citizenFilterChain`'s `authorizeHttpRequests`,
      `hasRole("CUSTOMER")` — the ownership check itself stays in
      `CitizenController`, same "role gate here, data-driven gate in the
      controller" split `workerFilterChain`'s own comment already
      documents for `WorkerCaseController`.
- [x] **Step 4: `CitizenDeterminationAccessTest`.** A citizen can read
      their own trace (200); a different citizen's token against the
      same determination id gets 403; an unauthenticated request gets
      401 — the same three-case shape Phase 1b's own row-level-auth test
      used for workers.
- [x] **Step 5: `grounding.py`.** `citation_grounded(answer_citations:
      list[str], retrieved_chunk_ids: list[str]) -> bool` — the
      deterministic pre-check from design doc §2.6, written once here so
      both this task's live serving path and Task 7's eval harness import
      the same function rather than each reimplementing it.
- [x] **Step 6: `llm_client.py` + `answer_general()`.** `LlmClient`
      (protocol: `generate(prompt: str, **params) -> LlmResponse`) and
      its sole implementation for now, `OllamaClient` — every later call
      site in this task, and every LLM call in Tasks 3/5/6, takes an
      `LlmClient` rather than talking to Ollama directly, so Task 9 can
      add a second implementation without touching any of them.
      `answer_general()` retrieves via Task 1's `hybrid_search`; if the
      top result's score is below a relevance threshold, returns
      `abstained=True` with the "insufficient information in the policy
      corpus" message and no LLM call at all (cheapest, most reliable
      form of abstention — don't even ask the model to try). Otherwise,
      calls `LlmClient.generate()` with retrieved chunks as clearly-
      delimited, labeled context
      (design doc §2.2's trusted/untrusted framing — nothing here is
      applicant-submitted, so the whole context is trusted, but the
      delimiting convention is established here for Step 7 to reuse where
      it matters more).
- [x] **Step 7: `answer_denial()`.** Calls the new
      `GET /api/my/determinations/{id}/trace` endpoint, extracts which
      DMN test failed from the trace's `decisionResults`, retrieves the
      CFR section governing that specific test (a targeted `hybrid_search`
      query built from the failed test's name, not the raw user
      question), and prompts the model to explain using the trace's own
      numbers (inserted as trusted data) plus the retrieved regulation
      text — the model never recomputes a number, only composes prose
      around numbers already decided.
- [x] **Step 8: `provenance.py`.** Persists every answer (both entry
      points) to a new `ai.policy_qa_answer` table in `canopica_operational`
      (a new schema in the existing shared Postgres — no new database,
      same "reuse existing infra" posture as pgmq/tokenize) via `psycopg`,
      written directly by this Python service using the existing `canopica_app`
      role (this is a first-party trusted service, not an external
      caller — no new role needed here the way `canopica_analytics_ro` is
      needed for Task 4's external-facing analytics surface). Columns:
      `id`, `question`, `answer`, `citations` (array), `abstained`,
      `corpus_version`, `embedding_model_version`, `retrieval_config`
      (jsonb: top-k, RRF/rerank settings), `prompt_version`,
      `generation_model`, `generation_params` (jsonb), `retrieved_chunk_ids`
      (array), `determination_id` (nullable — set only for the denial
      path), `created_at`.
- [x] **Step 9: `api.py` + `PolicyQaPage.tsx`.** FastAPI router:
      `POST /qa/ask` (general), `POST /qa/why-was-i-denied` (forwards the
      citizen's own bearer token to the API's new trace endpoint
      server-side — the AI service never receives a token it can use for
      anything beyond that one read). A minimal citizen-facing web page:
      a question box, an answer with visible citations, and (when
      abstained) the plain "insufficient information" message rendered
      distinctly from a real answer, not just plain text a user could
      mistake for a normal response.
- [x] **Step 10: `test_policy_qa.py`.** A grounded-answer case (question
      with a clear corpus match, citations present, `abstained=False`); an
      abstention case (question with no relevant corpus match);
      `answer_denial` against a seeded determination trace produces a
      citation from the correct CFR section for the specific test that
      failed; provenance row is written and complete for every answer.
- [x] **Step 11: Full suite + commit.**

---

## Task 3: Rule-authoring copilot

Proposes new `policy_parameter_set` values from a changed policy document
— narrowed scope per design doc §2.3, never DMN table restructuring.

**Amended 2026-08-23, during implementation.** Five corrections, each
found by writing the code rather than by re-reading the plan:

1. **Migration numbers.** `V13` was already taken by Task 2's
   `policy_qa_answer`. The proposal table is **`V14`**.
2. **Supersession needs its own migration.** Publishing a superseding
   parameter set is impossible as `V3` stands — the outgoing `SNAP-FY2026`
   set is open-ended (`effective_to = null`) and `V3`'s trigger refuses
   every UPDATE, so a new set would overlap it and `findEffectiveOn` would
   throw on the next determination. Settled by
   `docs/design/2026-08-23-policy-parameter-supersession.md` (Option A):
   add **`V15__policy_parameter_set_closeable.sql`**, narrowing the
   trigger to permit `effective_to` `null` → date and nothing else.
   `PolicyParameterImmutabilityTest` gains the boundary cases.
3. **`propose_parameter_changes` takes a third argument.** The signature
   below said `(document_excerpt, current_parameter_set_id)`, but Step 1's
   own prose already required the current values to be passed in (the AI
   service has no operational-Postgres access). Real signature:
   `(document_excerpt, current_parameter_set_id, current_values)`.
4. **No ADMIN user is seeded.** `identity/realm-export/canopica-workers-realm.json`
   defines the `ADMIN` role but seeds only `worker.sam` and
   `supervisor.robin`. Task 3's ADMIN-only routes need an admin identity
   to be testable or demoable at all, so the realm export gains one and
   `AbstractApiTest` gains an `adminToken()`.
5. **The proposal table carries provenance.** `generation_model`,
   `prompt_version` and `proposed_by` beyond the columns sketched below —
   the same bar `ai.policy_qa_answer` already holds (design doc §2.2),
   applied to a draft that can end up deciding a benefit amount. "An AI
   proposed it" is never a complete answer to who changed a figure.

**Files:**
- Create: `ai/src/canopica_ai/policy_intelligence/rule_authoring/service.py`,
  `schema.py`, `api.py`
- Create: `ai/tests/test_rule_authoring.py`,
  `ai/tests/test_rule_authoring_api.py`
- Create: `api/src/main/resources/db/migration/
  V14__policy_parameter_proposal.sql`,
  `V15__policy_parameter_set_closeable.sql`
- Create: `api/src/main/java/canopica/api/policy/
  PolicyParameterPublishService.java`
- Create: `api/src/main/java/canopica/api/api/
  PolicyParameterProposalController.java`
- Create: `api/src/test/java/canopica/api/policy/
  PolicyParameterPublishServiceTest.java`
- Create: `ui/src/pages/RuleAuthoringPage.tsx`
- Modify: `SecurityConfig.java` (new `ADMIN`-only routes)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.policy_intelligence.rule_authoring.service.
  propose_parameter_changes(document_excerpt: str, current_parameter_set_id:
  UUID) -> ParameterProposal`, a Pydantic model: `parameter_set_id` (the
  set being diffed against), `proposed_values: list[ProposedParameter]`
  (`name`, `household_size | None`, `old_value`, `new_value`, `unit`,
  `rationale: str`), `source_excerpt: str`. The API calls this over
  HTTP (`POST /rule-authoring/propose`) and never constructs one itself.
- Consumes: nothing from earlier AI tasks — this is independent of Task
  2's retrieval path, reading only the excerpt/diff supplied at call
  time (design doc §2.3's "supplied policy-document excerpt" mechanism).

```sql
-- V13__policy_parameter_proposal.sql
create table policy_parameter_proposal (
    id uuid primary key,
    current_parameter_set_id uuid not null references policy_parameter_set(id),
    source_excerpt text not null,
    proposed_values jsonb not null,
    status text not null check (status in ('PENDING', 'ACCEPTED', 'REJECTED')),
    reviewed_by text,
    reviewed_at timestamptz,
    published_parameter_set_id uuid references policy_parameter_set(id),
    created_at timestamptz not null default now()
);
-- Deliberately mutable (status/reviewed_by/reviewed_at/published_parameter_set_id
-- update in place as a human reviews) -- this is a review workflow record, not
-- a determination or a parameter value; V3's immutability trigger does not
-- apply here and must not be copied onto this table.
```

- [x] **Step 1: `schema.py` + `service.py`.** `ParameterProposal`/
      `ProposedParameter` Pydantic models; `propose_parameter_changes()`
      prompts the local Ollama model with the supplied excerpt and the
      current effective parameter values (fetched by the API, passed
      in the request — the AI service has no direct Postgres access,
      consistent with Task 2's provenance write being the *only* place
      this service touches a database, and only its own schema),
      requiring the model's response to conform to the schema (structured
      output — reject and retry once on a validation failure, then
      surface a clear "could not produce a valid proposal" error rather
      than a partially-applied one).
- [x] **Step 2: `V13` migration.**
- [x] **Step 3: `PolicyParameterPublishService`.** `propose(excerpt,
      currentSetId)` calls the AI service, persists a `PENDING`
      `policy_parameter_proposal` row. `review(proposalId, decision,
      reviewerName)`: on `REJECTED`, sets status/reviewer/timestamp only.
      On `ACCEPTED`, builds a new `PolicyParameterSet`/`PolicyParameter`
      rows from `proposed_values` and calls
      `PolicyParameterSetRepository.save()`/`PolicyParameterRepository.
      save()` — the same insert-only path the resolver already reads
      from — then stamps `published_parameter_set_id` on the proposal
      row. No other code path in this service can reach `.save()` on
      those two repositories with proposal data.
      **Amended:** the new set is *complete*, not a delta — it copies
      every `policy_parameter` row from the outgoing set and applies the
      accepted changes over the top, because `PolicyParameterResolver`
      needs the full parameter list to build a `SnapPolicyParameters`.
      And the same transaction closes the outgoing set at
      `newEffectiveFrom - 1 day` (V15, per the supersession design doc),
      so there is never a window with two open-ended sets. The reviewer
      supplies `versionLabel`, `effectiveFrom` and `sourceCitation` on
      accept: an effective date is a policy fact from the memo, not
      something to infer, and `version_label` is `unique`.
- [x] **Step 4: `PolicyParameterProposalController`.**
      `POST /api/policy/proposals` (ADMIN-only, body: excerpt),
      `POST /api/policy/proposals/{id}/review` (ADMIN-only, body:
      accept/reject).
- [x] **Step 5: `SecurityConfig`.** Both routes `hasRole("ADMIN")` —
      the narrowest existing role, since publishing a parameter version
      is a higher-stakes action than the caseload work `WORKER`/
      `SUPERVISOR` already do.
- [x] **Step 6: `PolicyParameterPublishServiceTest`.** Accepting a
      proposal produces a new, correctly effective-dated
      `policy_parameter_set` row reachable via the existing
      `PolicyParameterResolver`; rejecting one leaves the current
      effective set unchanged; a proposal with a value outside a sane
      bound (e.g. a negative dollar amount) fails schema validation
      before it ever reaches the database.
- [x] **Step 7: `RuleAuthoringPage.tsx`.** An admin pastes/uploads an
      excerpt, sees the proposed diff line-by-line (old value → new
      value, with the model's stated rationale), and accepts or rejects
      — no path that publishes without this explicit click.
- [x] **Step 8: `test_rule_authoring.py`.** A real policy-text excerpt (a
      synthetic but realistic COLA-style adjustment) produces a proposal
      whose values match what a human would read from that excerpt;
      malformed model output is rejected, not passed through.
- [x] **Step 9: Full suite + commit.**

---

## Task 4: MetricFlow semantic layer

The real prerequisite design doc §2.4 flags as absent: no
`semantic_models:`/`metrics:` YAML exists anywhere in this codebase yet.
Built before the Analytics Copilot that consumes it.

**Files:**
- Create: `data-platform/dbt/canopica_warehouse/models/semantic/
  semantic_models.yml`, `metrics.yml`
- Create: `ai/tests/test_metric_semantics.py`
- Modify: `data-platform/pyproject.toml` (+`dbt-metricflow`)
- Modify: `infra/postgres/init/01-databases.sql` (+`canopica_analytics_ro`)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: a validated MetricFlow manifest (`mf validate-configs` clean)
  covering all 5 gold marts (`mart_determination_outcomes`,
  `mart_payment_accuracy`, `mart_access_review`,
  `mart_processing_timeliness`, `mart_worker_caseload`) — the tool
  surface Task 5's MCP server exposes as callable tools, and the schema
  Task 5's authorization layer resolves a caller's tool list against.

```sql
-- infra/postgres/init/01-databases.sql addition
create role canopica_analytics_ro with login password 'canopica_analytics_ro';
grant connect on database canopica_serving to canopica_analytics_ro;
-- materialize_gold() (data-platform/src/canopica_data/serving/materialize.py)
-- runs as canopica_app and (re)creates every gold table on each pipeline run;
-- default privileges make every future materialization grant select
-- automatically, without touching materialize.py itself.
alter default privileges for role canopica_app in schema public
    grant select on tables to canopica_analytics_ro;
```

- [x] **Step 1: `semantic_models.yml`.** One `semantic_model:` entry per
      gold mart, declaring its `entities` (primary/foreign keys already
      established by each mart's own grain), `dimensions` (categorical
      and time columns — e.g. `program_code`, `determination_date`), and
      `measures` (the numeric columns each mart exists to report on —
      e.g. `mart_payment_accuracy`'s error-amount columns,
      `mart_processing_timeliness`'s `processing_days`).
- [x] **Step 2: `metrics.yml`.** Named, tested metrics built on those
      measures — e.g. `avg_processing_days`, `pct_missed_standard`,
      `determinations_by_outcome` — the vocabulary the NL-to-metric
      service (Task 5) resolves questions into; an unrecognized
      metric/dimension name simply isn't in this file, so the manifest
      itself rejects it (design doc §2.4's "fails validation, doesn't
      silently run against the wrong table").
- [x] **Step 3: `canopica_analytics_ro` role.** Added to
      `01-databases.sql`, verified `SELECT`-only (attempting an `INSERT`
      as this role fails) and structurally unable to reach any
      PII-shaped column (gold is already PII-free per Phase 1b's
      `no_pii_in_gold` test — this role inherits that property, doesn't
      need its own check).
- [x] **Step 4: `mf validate-configs` + a real local query.** Run
      `mf query --metrics avg_processing_days --group-by program_code`
      (or equivalent) against the local `canopica_serving` database populated
      by `make pipeline`, confirm it returns real, correct numbers —
      this task's own proof the semantic layer is wired to real data, not
      just schema-valid.
- [x] **Step 5: `test_metric_semantics.py`.** Validates the manifest,
      asserts every gold mart has a corresponding `semantic_model:` entry,
      and runs one real `mf query` against a seeded Testcontainers
      database (same fixture pattern as `test_mart_processing_timeliness.py`)
      confirming a known-good expected value.
- [x] **Step 6: Full suite + commit.**

---

## Task 5: Analytics Copilot

NL question → MCP tool call → MetricFlow query → result, with
authorization resolved before any query compiles.

**Files:**
- Create: `ai/src/canopica_ai/analytics_copilot/mcp_server.py`, `tools.py`,
  `service.py`
- Create: `ai/tests/test_analytics_copilot.py`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 4's MetricFlow manifest (via `mf query`'s Python API,
  never raw SQL); a worker-realm Keycloak JWT (validated the same way the
  API validates one, via the workers realm's JWKS endpoint — this
  service is its own resource server, not routed through the API).
- Produces: `canopica_ai.analytics_copilot.service.ask(question: str, jwt:
  str) -> AnalyticsAnswer` (Pydantic: `compiled_sql: str`, `result_rows:
  list[dict]`, `metric_names_used: list[str]`) — `compiled_sql` is always
  populated, satisfying design doc §2.4's "generated SQL always shown"
  without separate tooling, since it's MetricFlow's own compiled output,
  never LLM-written.

- [x] **Step 1: `tools.py`.** Builds the MCP tool list *per caller role*
      — resolved from the JWT's realm roles before any tool is even
      offered to the LLM, not filtered after (design doc §2.4's
      "authorization before query compilation"). For Phase 2's scope,
      `WORKER`/`SUPERVISOR`/`ADMIN` all get the same tool list (every
      metric in Task 4's manifest is already caseload-aggregate, not
      row-level PII); the role check exists as the enforcement point for
      any future metric that needs narrowing, not because today's metrics
      differ by role — stated explicitly so a later reader doesn't wonder
      why the check looks like a no-op today.
- [x] **Step 2: `mcp_server.py`.** Exposes each metric from Task 4's
      manifest as one MCP tool (`query_metric`, with `metric_name`,
      `group_by`, `filters` as typed parameters, validated against the
      exact names in Task 4's `metrics.yml` — an LLM-hallucinated metric
      name fails tool-argument validation before `mf query` ever runs).
- [x] **Step 3: `service.py`.** `ask()` runs the LLM (local Ollama, tool-
      calling mode) against the role-scoped tool list from Step 1; the
      model's only job is picking a tool + arguments, never writing SQL
      itself. The selected tool call executes via MetricFlow's Python
      query engine; `compiled_sql` comes from MetricFlow's own explain/
      compile output, not from the LLM.
- [x] **Step 4: `canopica_analytics_ro` connection.** The MetricFlow query
      engine connects to `canopica_serving` as `canopica_analytics_ro` (Task 4's
      role) — the defense-in-depth backstop design doc §2.4 calls for,
      underneath the tool-exposure-time check from Step 1, not the sole
      gate.
- [x] **Step 5: `test_analytics_copilot.py`.** A real NL question
      ("what's the average processing time for SNAP determinations last
      month") resolves to the correct metric/dimension and a real,
      correct number against seeded data; a request for a
      nonexistent/hallucinated metric name fails tool validation, not
      silently falls back to something else; a request using
      `canopica_analytics_ro`'s connection to attempt a raw write (test-only,
      proving the backstop) is rejected at the database level.
- [x] **Step 6: Full suite + commit.**

---

## Task 6: Dashboard-authoring assist

An authoring-time CLI, not a live service — a BI developer runs it
locally, reviews the diff like any other PR, and applies it via Tabular
Editor's existing publish step. No new mechanism; slots into the
model-as-code pattern Phase 1a's Task 11 already built.

**Files:**
- Create: `ai/src/canopica_ai/dashboard_assist/cli.py`, `service.py`
- Create: `ai/tests/test_dashboard_assist.py`
- Create: `reporting/semantic-model/proposals/` (output directory,
  `.gitkeep`)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: the existing TMDL files under `reporting/semantic-model/`
  (read-only — this task never writes into the live model files
  directly).
- Produces: `canopica_ai.dashboard_assist.service.propose_dashboard(prompt: str)
  -> DashboardProposal` (Pydantic: `new_measures: list[DaxMeasure]`
  (`name`, `dax_expression`, `table`), `new_visuals: list[VisualSpec]`,
  `rationale: str`), written by the CLI as a `.tmdl`-formatted patch file
  under `reporting/semantic-model/proposals/`.

- [x] **Step 1: `service.py`.** Reads the current TMDL files as context,
      prompts the local Ollama model with the existing model's tables/
      measures plus the user's natural-language ask ("add a measure for
      average processing time by county"), requires the response to
      conform to `DashboardProposal`'s schema.
- [x] **Step 2: `cli.py`.**
      `uv run python -m canopica_ai.dashboard_assist.cli propose --prompt "..."`
      writes the proposal as a timestamped `.tmdl`-formatted file into
      `reporting/semantic-model/proposals/` — reviewable via `git diff`
      against the real model, never written into the live model files.
      `reporting/README.md` (or a new short section in it) documents the
      manual next step: a human reviews the proposal file, hand-applies
      the accepted parts into the real TMDL files (or uses Tabular
      Editor's CLI to script the merge), and the existing publish step
      pushes it live — unchanged from Phase 1a's Task 11.
- [x] **Step 3: `test_dashboard_assist.py`.** A prompt produces a
      schema-valid proposal referencing a real existing table from the
      current TMDL model (not a hallucinated one — assert the proposal's
      `table` field always matches a name actually present in
      `reporting/semantic-model/`); a malformed model response is
      rejected, not written to disk as a proposal file.
- [x] **Step 4: Full suite + commit.**

---

## Task 7: Eval-suite CI gate

RAGAS metrics, DeepEval-gated, baseline-relative thresholds, plus the
deterministic citation pre-check from Task 2 — all against Policy Q&A,
the only AI capability this phase evaluates with a golden set (design doc
§2.6 scopes the eval suite to Policy Q&A specifically).

**Files:**
- Create: `ai/src/canopica_ai/policy_intelligence/eval/golden_set.yaml`,
  `run_eval.py`, `baseline.json`
- Create: `ai/tests/test_eval_gate.py`
- Modify: `.github/workflows/ci.yml` (+`ai-eval` job)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 2's `answer_general()` (called once per golden question);
  Task 2's `grounding.citation_grounded()` (the deterministic pre-check,
  reused, not reimplemented).
- Produces: a CI-blocking job; `baseline.json` is a committed artifact a
  future task deliberately updates when the system's retrieval or
  generation genuinely improves (a manual, reviewed update — never
  auto-written by the eval run itself, or a regression could silently
  reset its own floor).

```yaml
# golden_set.yaml (shape)
- question: "What is the gross income limit for a household of 3?"
  expected_cfr_sections: ["273.9"]
- question: "How is the shelter deduction capped?"
  expected_cfr_sections: ["273.9"]
# ~20 total, spanning every scoped CFR area from design doc §2.1
```

- [x] **Step 1: `golden_set.yaml`.** ~20 hand-authored Q&A pairs against
      Task 1's scoped corpus, each recording the CFR section(s) a correct
      answer should retrieve — covers gross/net income, every deduction
      type, categorical eligibility, and expedited processing, matching
      the corpus's own scope from Task 1 exactly (no golden question
      about a section the corpus doesn't index).
- [x] **Step 2: `run_eval.py`.** For each golden pair: calls
      `answer_general()`, runs RAGAS's faithfulness/context-precision/
      context-recall metrics via DeepEval's evaluation API against the
      question/answer/retrieved-context triple, and runs Task 2's
      `citation_grounded()` as a pre-check (a fabricated citation fails
      immediately, no LLM-judge call spent on it — design doc §2.6's
      "cheap, zero-noise pre-check" ordering). Aggregates to mean scores
      per metric.
- [x] **Step 3: `baseline.json` + threshold logic.** First run against
      `main` establishes the baseline; `run_eval.py --check` (CI mode)
      fails if any metric's mean score falls more than a fixed margin
      (e.g. 5 percentage points — the exact margin is this task's own
      implementation-time pick, documented inline in `run_eval.py`)
      below `baseline.json`'s recorded value — the baseline-relative
      gating design doc §2.6 specifies, not an absolute score floor.
- [x] **Step 4: `ai-eval` CI job.** Runs `run_eval.py --check` against
      the local Ollama model in CI. **Revised at implementation time**
      (design doc §2.6 addendum): the judge model is hosted OpenRouter,
      not local Ollama — the local judge was measured too slow and
      unreliable for a CI-blocking gate. The generation model under test
      stays local/self-hosted, unchanged; only the judge is remote.
      Blocks merge on failure, same bar as every other CI job per
      CLAUDE.md's testing policy.
- [x] **Step 5: `test_eval_gate.py`.** A deliberately-broken fixture (a
      fabricated citation injected into a test answer) fails the
      deterministic pre-check, proving the gate actually gates before any
      CI run depends on it; `run_eval.py --check` against the real,
      unmodified system passes clean.
- [x] **Step 6: Full suite + commit.**

---

## Task 8: AI observability

Extends the existing Phase 1b OTel/Jaeger/Prometheus/Grafana stack —
`gen_ai.*` semantic-convention spans around every LLM and retrieval call
from Tasks 1, 2, 3, 5, and 6, plus a live per-request
`rag_citation_grounded` attribute. No new observability tool.

**Files:**
- Create: `ai/src/canopica_ai/common/observability.py`
- Create: `ai/tests/test_ai_observability.py`
- Modify: `ai/src/canopica_ai/policy_intelligence/retrieval.py` (Task 1),
  `qa/service.py` (Task 2), `rule_authoring/service.py` (Task 3),
  `analytics_copilot/service.py` (Task 5), `dashboard_assist/service.py`
  (Task 6) — each wraps its LLM/retrieval call in a span
- Modify: `infra/docker-compose.yml` (`ai`-side services get
  `CANOPICA_OTLP_TRACES_ENDPOINT` pointed at the existing `jaeger` service —
  no new Jaeger config)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.common.observability.traced_llm_call(span_name: str,
  model: str, **gen_ai_attrs)` and `traced_retrieval_call(span_name: str,
  **attrs)` — context managers mirroring
  `canopica_data.observability.tracing.traced()`'s own shape (`SimpleSpanProcessor`,
  OTLP/HTTP export), so a reader who already knows `data-platform`'s
  pattern recognizes this one immediately, not a second, differently-
  shaped tracing convention.

- [x] **Step 1: `observability.py`.** Same OTel SDK setup
      `data-platform`'s `tracing.py` already established
      (`SimpleSpanProcessor`, not `BatchSpanProcessor`, for the same
      short-lived-process reasoning that file's own code comment states)
      — reimplemented here rather than imported cross-project, since
      `ai/` and `data-platform/` are separate `uv` projects with no
      shared internal package today (introducing one now, for two call
      sites, would be the premature-abstraction CLAUDE.md's conventions
      warn against). `gen_ai.*` attribute names verified against OTel's
      then-current spec at implementation time — design doc §2.8's own
      stated caveat, not assumed from this plan.
- [x] **Step 2: Wrap every LLM/retrieval call site.** `retrieval.hybrid_
      search()` gets a `traced_retrieval_call` span (`gen_ai.request.
      model` = embedding model, plus `db.system=opensearch`-style
      attributes for the search itself); every `service.py`'s LLM
      prompt call gets a `traced_llm_call` span (`gen_ai.request.model`,
      `gen_ai.usage.input_tokens`/`output_tokens` from Ollama's own
      response metadata, `gen_ai.response.finish_reason`) — additive
      wrapping around existing call sites, no logic changes, same
      "wraps without touching" discipline Phase 1b's Task 9 already
      applied to the API/pipeline.
- [x] **Step 3: `rag_citation_grounded` attribute.** Task 2's
      `answer_general()`/`answer_denial()` set this boolean attribute on
      their own span using the exact same `grounding.citation_grounded()`
      function Task 7's CI gate calls — a live, per-request signal in
      Grafana on top of the CI gate's aggregate one, design doc §2.8's
      explicit requirement, sharing logic rather than duplicating it.
- [x] **Step 4: `test_ai_observability.py`.** A real question against
      `answer_general()` produces a trace in Jaeger with both a retrieval
      span and a generation span, the generation span carrying
      `gen_ai.request.model` and a populated `rag_citation_grounded`
      attribute — same live-poll-Jaeger-API pattern
      `data-platform/tests/test_observability.py` already established,
      not a mock.
- [x] **Step 5: Full suite + commit.**

---

## Task 9: Public hosted demo

Policy Q&A's general-question path (only — "why was I denied" needs an
authenticated citizen's own determination, so it stays behind login, not
on the public surface) goes live at a public URL. Tiered OpenRouter
fallback, guardrails, and the app-level rate limiter design doc §2.10
requires for the one unauthenticated surface in this phase.

**Files:**
- Create: `ai/src/canopica_ai/public_demo/app.py`, `static/index.html`,
  `rate_limit.py`
- Create: `ai/src/canopica_ai/common/guardrails.py`
- Modify: `ai/src/canopica_ai/common/llm_client.py` (Task 2's Ollama-only
  client gains an OpenRouter-backed implementation behind the same
  interface, selected by config)
- Create: `ai/tests/test_public_demo.py`
- Create: `infra/fly/fly.toml`, `infra/fly/Dockerfile.public-demo`
- Modify: `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`
  (only if this task's concrete hosting pick — Fly.io — needs recording
  beyond what §2.7/§4.16 already state; check first, most of this is
  already written)
- Modify: `README.md` (a real, live public demo link — the README's own
  "Status & roadmap" section gets this, same as every prior task's
  README refresh)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.common.llm_client.LlmClient` (protocol: `generate(
  prompt, **params) -> LlmResponse`) with two implementations —
  `OllamaClient` (Task 2, unchanged) and `OpenRouterTieredClient` (this
  task) — selected by `Settings().inference_mode` (`local` | `public_demo`),
  so every earlier task's call sites need zero changes to run in either
  mode.

- [x] **Step 1: `OpenRouterTieredClient`.** Tries the pinned `:free`-
      tagged model first; on a rate-limit response, falls back to a
      pinned cheap paid model for that one request; tracks cumulative
      paid spend for the current month (a simple counter, persisted — a
      file or a Postgres row is enough for this scale, not a metering
      service) and stops falling back to paid once the running total
      approaches the $5 cap, reverting to free-tier-only; once free-tier
      is *also* rate-limited, raises a typed
      `InferenceUnavailableError` the caller renders as "temporarily
      unavailable" — the three-tier shape design doc §2.7/§2.10 specify
      exactly, implemented once, at the client layer, so nothing above it
      needs tier-aware logic. **Which paid model, decided 2026-08-26**
      (`docs/STATUS.md`'s "Public demo inference" row): the pinned
      paid-tier model is a `Settings()` config value, not hardcoded —
      `deepseek/deepseek-chat` for the rest of active development,
      repointed to `anthropic/claude-haiku-4.5` in the same commit as the
      public-repo flip. Both are OpenRouter models behind this same
      client, so implement the model name as configurable from the
      start; the later swap should need no code change.
- [x] **Step 2: `guardrails.py`.** An input check (blocks obvious
      prompt-injection/off-topic-abuse patterns — a small classifier
      prompt against the same local/tiered model, cheap since it's one
      short call) and an output check (re-verifies the generated answer
      doesn't contain anything outside the trusted-context boundary
      before it's returned) — applied only in `public_demo/app.py`'s
      request path, on top of Task 2's existing grounding/abstention
      logic, not a replacement for it.
- [x] **Step 3: `rate_limit.py`.** A thin per-session/day limiter (e.g.
      an in-memory or Postgres-backed counter keyed by a session cookie)
      in front of the whole tiered chain, so a limiter-triggered response
      is a clean UX message, not a raw upstream 429.
- [x] **Step 4: `public_demo/app.py` + `static/index.html`.** A minimal
      FastAPI app mounting the static page and one endpoint
      (`POST /demo/ask`) that calls Task 2's `answer_general()`
      configured with `inference_mode=public_demo` — the general-
      question path only; no login, no "why was I denied" link on this
      surface.
- [ ] **Step 5: Fly.io deploy.** `infra/fly/Dockerfile.public-demo`
      bundles the `public_demo` app plus a pre-ingested OpenSearch data
      volume (Task 1's corpus, indexed once and shipped, not re-ingested
      on every deploy); `fly.toml` configures the app + a small OpenSearch
      process **+ Ollama, serving only the embedding model** on the same
      always-on instance (design doc §2.7's "small always-on host," ~$5/mo
      real cost, not free — see that section's 2026-08-26 correction —
      revisit only if the combined memory footprint doesn't fit, per that
      section's own stated fallback plan). **Corrected 2026-08-26,
      caught before writing the Dockerfile**: `hybrid_search()` calls
      `embed_text()`, which always calls Ollama for the query embedding
      regardless of `inference_mode` -- `inference_mode` only selects the
      *generation* client (`build_llm_client`), never the embedding path.
      §2.7's own "App + retrieval hosting: embeddings, OpenSearch, and the
      FastAPI app" already named embeddings as something the host runs;
      this step's file list just hadn't translated that into "Ollama
      needs to run here too" until now. Generation still goes through the
      tiered OpenRouter client -- only retrieval's embedding step is
      local, keeping citation grounding fully deterministic and matching
      §2.7's actual intent, not a scope change. Deploy for real; confirm
      the live URL answers a real question end to end. Per the user's
      2026-08-26 sequencing decision, this step's *files* (Dockerfile,
      fly.toml) are built and locally verified (`docker build`/`docker
      run`, no Fly.io account interaction) today along with the rest of
      Task 9 -- the actual `fly deploy` is held until the repo is close
      to going public (see `docs/STATUS.md`'s Open Questions).
- [ ] **Step 6: `test_public_demo.py`.** Local (non-deployed) tests: the
      tiered client actually falls back on a simulated rate-limit
      response (mocked OpenRouter, not a real account call in CI); the
      spend-cap counter stops the paid fallback once exceeded; a
      guardrail-triggering input is blocked before reaching the model; a
      real request against `app.py`'s local test client returns a
      grounded answer with citations, unchanged behavior from Task 2's
      own general-question path.
- [ ] **Step 7: Full suite + commit, then the live Fly.io smoke check**
      (not part of CI — a one-time, by-hand verification the same way
      Phase 1a's Task 13 walked `docs/demo.md` by hand): open the public
      URL, ask a real question, confirm citations render, confirm the
      "insufficient information" abstention path renders distinctly for
      an out-of-scope question. Record what was actually observed in
      `docs/STATUS.md`'s verification row, the same "demoed, not just
      described" standard every prior phase-closing task has met.

---

## Phase 2 definition of done

- [ ] `make test`, `make lint` pass from a clean clone, `ai/` fully
      wired into both.
- [ ] A real question against the local stack returns a grounded,
      cited answer; an out-of-scope question abstains instead of
      guessing.
- [ ] A citizen can read their own "why was I denied" explanation,
      citing both their real determination numbers and the governing
      CFR section; a different citizen's token cannot reach it.
- [ ] A rule-authoring proposal, once accepted, publishes a new
      effective-dated `policy_parameter_set` reachable by the existing
      resolver; rejecting one changes nothing.
- [ ] `mf query` runs locally against all 5 gold marts; the Analytics
      Copilot answers a real NL question with the compiled SQL always
      shown, and a hallucinated metric name fails tool validation, not a
      silent wrong-table query.
- [ ] The dashboard-authoring CLI produces a reviewable TMDL patch file,
      never a live model change.
- [ ] `ai-eval` is a real, CI-blocking job with a committed baseline; a
      deliberately-broken citation fails it.
- [ ] A real Policy Q&A request produces `gen_ai.*` spans in Jaeger,
      including a live `rag_citation_grounded` attribute.
- [ ] The public demo is live at a real Fly.io URL, answers a real
      question, and its tiered fallback/guardrails/rate limiter are all
      exercised by tests (fallback/cap by mock, guardrail block by a
      real blocked input).
- [ ] `docs/STATUS.md`, `CLAUDE.md`, and `README.md` all reflect
      reality, including the README's Mermaid diagram if the AI layer's
      shape changed from what it already shows.

## Deferred out of Phase 2, on purpose

Recorded so a later session doesn't read an absence as an oversight:
Document Intake, Correspondence Drafting, Fraud Risk Triage, SLA/
Compliance Monitor, QC Assistant, and SOP Copilot (all Phase 3/4, per
roadmap §5); query rewriting/expansion ahead of retrieval and a
structured thumbs-up/down feedback loop on Policy Q&A answers (design
doc §2.10, "considered, deliberately deferred" — additive scope for a
later phase, not missing from this one); DMN decision-table
*restructuring* by the rule-authoring copilot (§2.3's real scope
narrowing — parameter values only, this phase and likely permanently,
not just "not yet"); a true multi-step autonomous agent anywhere in this
phase (§2.10's bounded-pipeline architectural stance); `mart_fairness_
audit` (still Phase 4, unchanged from Phase 1b's own deferral); and any
identity proofing, sensitive-case sealing, or access recertification
beyond what Phase 1b already built (unrelated to this phase, still open
from Phase 1b's own deferred list).
