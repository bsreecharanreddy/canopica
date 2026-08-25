# Canopica — Phase 2 Policy Intelligence & Analytics AI: Design Decisions

## 1. Scope recap

Phase 2, per the roadmap doc (§ Phase 2 — Policy Intelligence & Analytics
AI): OpenSearch policy-corpus retrieval, Policy Q&A/explainability RAG, a
rule-authoring copilot, an Analytics Copilot over MetricFlow, dashboard-
authoring assist, an eval-suite CI gate, and the public hosted demo going
live. Same governing principle as everywhere else in this repo: AI drafts,
flags, and explains; deterministic systems and human reviewers own every
binding decision. This doc settles the real forks — the mechanism
decisions an implementation plan can't be written without — the same way
`2026-08-22-phase-1b-hardening-design.md` did for Phase 1b. It does not
plan file-by-file; that's the implementation plan's job, next.

Checked against current (2026) industry practice for RAG retrieval, RAG
evaluation, text-to-metric copilots, and LLM observability before being
finalized — five real revisions came out of that pass (RRF fusion +
reranking in §2.1, RAG answer provenance in §2.1/§2.2, MCP + compile-time
authorization in §2.4, RAGAS/DeepEval-based gating in §2.6, and an
experimental-spec caveat in §2.8), noted inline where they apply rather
than silently folded in as if they were the original brainstorm's own
conclusions.

## 2. Decisions

### 2.1 OpenSearch corpus & retrieval

**What gets indexed**: the real public federal text — 7 CFR Part 273
(Certification of Eligibility, SNAP), pulled from eCFR/GovInfo (both
public, machine-readable, no scraping-ToS concern) — not this repo's own
`policy_parameter_set` values or DMN documentation. Real external text
matches the project's own stated identity ("real (public) policy
parameters instead of invented ones," README's "Why this exists") and
gives the eval suite (§2.6) something externally verifiable to grade
citations against; grading against this repo's own internal values would
be circular — the system would be citing itself.

**Which sections**: scoped to the sections this project's own rules
engine actually implements — gross/net income tests, the standard/earned-
income/dependent-care/medical/shelter deductions, categorical eligibility,
expedited processing (7 CFR 273.2(i), already real per Phase 1b Task 6) —
not the entirety of Part 273 (which also covers interstate transfers,
disqualification/IPV hearings, and other things this project doesn't
model). Keeps the corpus a real but bounded size appropriate for a
portfolio eval set, and keeps every citation traceable to something the
rules engine can also point at — the same regulation the DMN trace is
already implementing, not a disconnected second policy universe.

**Chunking**: at the CFR's own subsection level (e.g., `273.9(c)(1)`), not
a fixed-token window. CFR section numbers are already citation-grade
identifiers — "why was I denied" can cite `273.9(c)(1)` directly and a
reader can verify it against the real regulation, which a token-window
chunk boundary can't offer. Each OpenSearch document carries `cfr_section`,
`heading`, and `text` fields — `text` indexed for both BM25 lexical search
and k-NN vector search (embedded via the Ollama embedding model), the
hybrid retrieval the roadmap doc's own cross-cutting table already calls
for.

**Fusion + reranking** (added after checking this section against current
retrieval practice, not in the original brainstorm): hybrid retrieval
alone isn't the full production baseline as of 2026 — how the two result
sets combine matters. Naive score-averaging is a known failure mode
(BM25 and cosine-similarity scores aren't on comparable scales);
**Reciprocal Rank Fusion (RRF)**, which fuses by rank rather than raw score,
is the standard fix and is what actually gets configured. A **reranking**
pass — a cross-encoder scores each RRF-fused candidate against the query,
top 3-5 survive to generation — sits after fusion and before generation;
published benchmarks show a real, material accuracy gain from adding it
(not a marginal one), so it's treated as baseline here, not a later
optimization. OpenSearch has both RRF fusion and a reranking search-
pipeline processor built in — this is a pipeline configuration choice
against infrastructure already chosen, not a new system to stand up.

**Provenance**: every generated answer records the corpus version,
embedding-model version, and retrieval config (top-k, fusion method) that
produced it, alongside the answer itself — the same discipline design doc
§3.5 already applies to determinations and `policy_parameter_set`, applied
here so a Policy Q&A answer is reconstructible after the fact the same way
a benefit determination already is, not the one un-versioned thing in an
otherwise reproducibility-first system. Recorded once here; §2.2 is where
it's produced (every answer, both entry points).

### 2.2 Policy Q&A / explainability RAG

Two entry points share one retrieval+generation core, but "why was I
denied" is not a fresh retrieval-only Q&A:

- **General policy question** ("what's the income limit for a household
  of 3") — top-k retrieval over §2.1's corpus, answered grounded only in
  retrieved text.
- **"Why was I denied"** — seeded by the applicant's own real, persisted
  DMN trace (Phase 1a Task 5) merged with retrieval: the specific test
  that failed in the trace drives retrieval of the CFR section governing
  that specific test, so the explanation cites both the actual computed
  numbers (from the trace — deterministic, already correct, never
  recomputed by the LLM) and the regulation behind them (from retrieval).
  The LLM's only job is composing a plain-language explanation of numbers
  and citations that are already correct — the concrete mechanism that
  keeps this feature on the "explains, never decides" side of the
  governing principle, not just an assertion that it does.

**Threat-model application** (boundary already decided, roadmap §3.3 —
applied concretely here, not re-litigated): the DMN trace and CFR corpus
are trusted context; retrieval results and trace values are inserted into
the prompt as clearly-delimited data, never concatenated as if they were
trusted instructions. Nothing applicant-submitted (free-text fields, if
any) shares that trusted channel.

**Provenance** (§2.1's closing paragraph, made concrete): every answer's
persisted record carries `corpus_version`, `embedding_model_version`,
`retrieval_config` (top-k, RRF + rerank settings), `prompt_version`, the
generation model name/params (temperature, etc.), and the actual chunk
IDs retrieved for that answer — not just the answer text. Prompt/model
versioning is included alongside retrieval versioning, not as an
afterthought: a reproducibility record that captures *what was retrieved*
but not *what prompt and model turned it into an answer* is only half a
record. This is what makes "why did the system say this" itself
answerable after the fact, the same bar Phase 1a's determination trace
already clears for a benefit amount; a Policy Q&A answer with no such
record would be the one place in this repo where "how did we get this
number/citation" isn't reconstructible.

**Grounding / abstention**: when retrieval returns nothing above a
relevance threshold for a question, the system says so directly —
"insufficient information in the policy corpus to answer this" — rather
than generating a best-effort answer from weak or irrelevant context. This
is the standard fix for RAG's most common failure mode (a fluent, cited-
looking answer built on retrieval that didn't actually find anything
relevant) and was missing from the original brainstorm; without it, a
low-confidence retrieval and a confident retrieval look identical to the
end user, which is exactly backwards for a "why was I denied" feature
where an ungrounded guess is worse than no answer.

### 2.3 Rule-authoring copilot — a real scope narrowing

The roadmap's literal wording — "proposes a DMN decision-table diff" — is
narrowed here to: **proposes new `policy_parameter_set` values** (dollar
thresholds, deduction amounts, standard deductions) from a changed policy
document, not open-ended DMN decision-table restructuring. Recorded
explicitly as a correction, the same class of finding as Phase 1b Task 7's
own PII-tokenization scope narrowing — found before writing code, not
silently implemented differently from what the roadmap says.

**Why**: design doc §3.5 (temporality/reproducibility) already built
exactly the mechanism this needs — effective-dated, immutable-once-
published parameter versions. A copilot that proposes a new parameter
version, diffed against the current effective one, for a worker/admin to
review and publish fits that model exactly and stays on the "drafts,
human publishes" side of the governing principle using machinery that
already exists. Restructuring DMN table *logic* — new rules, new columns
— is a fundamentally bigger, higher-risk surface (the decision logic
itself, not its parameters) that this phase does not take on. Real-world
grounding: USDA republishes SNAP's COLA-adjusted parameter values
annually — "policy changed, update the numbers" is the actual, common
case this copilot exists for, not a hypothetical.

**Mechanism**: the LLM reads a supplied policy-document excerpt (or a
diff between two versions of the indexed §2.1 corpus), extracts candidate
parameter changes and a rationale, and presents them as a diff against
the current effective `policy_parameter_set`. A worker/admin reviews
line-by-line and either accepts — publishing a new effective-dated
version through the exact same insert-only path Phase 1a's resolver
already uses — or rejects. No path auto-publishes.

### 2.4 Analytics Copilot

**A real prerequisite, confirmed absent**: no MetricFlow `semantic_models:`
/`metrics:` YAML exists in this codebase yet — `data-platform/tests/
test_semantic_model.py` tests the *TMDL* Power BI model (Phase 1a Task 11),
a separate thing; `metricflow` is present in the venv only as a transitive
dependency, unused. This task must build the MetricFlow semantic model
against the existing gold marts (`mart_processing_timeliness`,
`mart_payment_accuracy`, `mart_worker_caseload`, `mart_access_review`,
`mart_determination_outcomes`) from scratch — a second, parallel semantic
layer describing the same gold marts for a second consumer, the same
"several BI tools over one governed warehouse" pattern this project
already applies with Power BI + Metabase.

**NL-to-metric mechanism**: MetricFlow's semantic layer is exposed to the
LLM as callable tools over **MCP** (Model Context Protocol) — the metric/
dimension names it can select from are tool definitions, not prose stuffed
into a prompt; this is the standard 2026 integration shape for exactly
this pattern (LLM ↔ governed semantic layer), not a bespoke mechanism.
Execution goes through MetricFlow's own query engine (`mf query` or its
Python API) — never LLM-generated raw SQL, which the roadmap doc already
rules out explicitly, and which a 2026 dbt Labs benchmark backs up
concretely: grounding in a semantic layer closed the text-to-SQL accuracy
gap from 90.0%→98.2% (Claude) and 84.1%→100% (GPT) against the same
questions. This gets two things for free: the manifest itself rejects an
unrecognized metric/dimension the LLM hallucinates (fails validation,
doesn't silently run against the wrong table), and MetricFlow's own
compiled-SQL output satisfies "generated SQL always shown" without
separate tooling.

**Authorization**: enforced at the MCP tool-exposure layer first — which
metrics/dimensions/rows a given caller's tool list even contains is
resolved from that caller's own role before any query is compiled, current
practice for exactly this reason (governance applied before SQL is
emitted catches what a query-time check can only catch after the fact).
A new least-privilege Postgres role, `canopica_analytics_ro` (`SELECT`-only on
the serving-layer gold schema, mirroring `canopica_app`'s own least-privilege
pattern from Phase 1a), sits underneath as a defense-in-depth backstop —
not the sole enforcement point.

### 2.5 Dashboard-authoring assist

The LLM proposes a dashboard spec (new visuals + DAX measures) as a
reviewable diff to the existing TMDL model-as-code files — the same
"reviewable in a diff" property the semantic model already has since
Phase 1a Task 11 — never auto-pushed to the live Power BI Service. A human
reviews the TMDL diff like any other PR; Tabular Editor's free CLI applies
it to a local/dev model file; an explicit, already-existing publish step
pushes it live, unchanged from today. No new mechanism needed — the
copilot's output slots into the model-as-code + human-review pattern that
already exists.

### 2.6 Eval-suite CI gate

**RAGAS metrics, DeepEval for CI gating, a deterministic pre-check
underneath** — revised from an earlier deterministic-only draft after
checking current practice: RAGAS's metric set (faithfulness, context
precision, context recall, answer relevancy) is the defined standard for
RAG evaluation, and DeepEval is the standard tool for gating on it in CI.
The concern the earlier draft was designed around — an LLM judge is
non-deterministic, so CI shouldn't flake on it — is real, but the
solved-in-practice answer isn't avoiding LLM-judged metrics for gating,
it's **baseline-relative thresholds**: run the eval against current
`main`, set the floor slightly below that result, so a genuine regression
trips the gate and ordinary judge noise doesn't. Still matches CLAUDE.md's
"run in CI and block a merge on regression, not just get described in a
doc" bar — it's just gated on a different kind of check than a `dbt test`.

A golden set of roughly 20 hand-authored Q&A pairs against §2.1's scoped
CFR sections, each recording the CFR section(s) a correct answer should
retrieve, feeds:

- **Faithfulness** (RAGAS/DeepEval, CI-blocking, baseline-relative
  threshold) — decomposes the generated answer into individual claims and
  verifies each against retrieved context; catches citing the *right*
  section but misstating what it says, which a citation-existence check
  alone cannot.
- **Context precision/recall** (RAGAS/DeepEval, same gating treatment) —
  does the golden pair's expected CFR section actually appear in the
  top-k retrieved chunks, and how much of what's retrieved is actually
  relevant.
- **Citation grounding** (deterministic, kept from the earlier draft as a
  cheap, zero-noise pre-check, not the whole gate) — does every citation
  the generated answer emits correspond to a chunk actually retrieved for
  that query; catches a literally-fabricated citation ID for free, before
  spending an LLM-judge call on it.

**Addendum (2026-08-24, implementation time): the judge model is hosted
OpenRouter, not local Ollama.** The implementation plan's Task 7 assumed
reusing this repo's own local `llama3.2:3b` as judge, at no extra cost.
Live measurement against the real corpus found that unusable for a
CI-blocking gate: a single golden question's `FaithfulnessMetric` call
took multiple minutes, and a subsequent metric on the same question
exceeded a 240s timeout and crashed the run outright. A judge never
serves user traffic — it grades an already-generated answer, once, in
CI — so this doc's "self-hosted, $0" posture for the *generation* model
under test (§2.2, unchanged) does not carry over to it. Pinned to
`nvidia/nemotron-3-ultra-550b-a55b:free`, chosen over OpenRouter's own
`openrouter/free` auto-router after that router was observed, live,
picking a safety-classifier model that silently ignored a real prompt
instead of answering it — see `judge_model.py`'s own docstring for the
exact probe and `run_eval.py`'s for the full CI-time investigation this
also drove (pipelined judging, a stratified 8-question CI subset).
Recorded in `docs/STATUS.md`'s decisions table.

### 2.7 Public hosted demo

Settled through direct back-and-forth on the real tradeoff (genuinely
free vs. reliably fast for a stranger clicking a link cold — LLM
inference needs real compute either way):

- **Tiered fallback, clarified after direct discussion**: OpenRouter's
  `:free`-tagged models are the primary path (exact tag pinned at
  implementation time against OpenRouter's then-current free catalog, not
  hardcoded here). On a free-tier rate-limit response, the request falls
  back to a cheap *paid* OpenRouter model for that one request, rather
  than failing closed immediately — a small, hard-capped paid overflow
  gives real availability exactly when free-tier limits are most likely
  to bite (a burst of real traffic, e.g. several people trying the demo
  in a short window), for a fully bounded cost. This is a deliberate
  revision from an earlier draft that treated the $5/mo cap as an
  emergency-only backstop expected to sit at $0 — free-tier-only-then-
  fail-closed would show "unavailable" during exactly the moments a real
  visitor is most likely to hit it.
- **Spend cap and fail-closed order**: the OpenRouter account's $5/month
  hard cap governs the paid-fallback path specifically — once cumulative
  paid usage for the month approaches it, the app stops falling back to a
  paid model and returns to free-tier-only; *then*, only once free-tier
  is also rate-limited, does it fail closed to a clear "temporarily
  unavailable" response. Three tiers, not two: free → cheap paid,
  capped → unavailable. A thin app-level per-session/day limiter still
  sits in front of the whole chain for a clean UX message rather than a
  raw upstream error at any tier.
- **App + retrieval hosting**: embeddings, OpenSearch, and the FastAPI
  app itself run on a small always-on free/cheap host — a Task-level
  implementation pick (e.g., Fly.io/Render free tier), not a phase-level
  fork; revisit only if OpenSearch's memory footprint doesn't fit.

### 2.8 AI observability

Extends the existing Phase 1b Task 9 OTel/Jaeger/Prometheus/Grafana stack
rather than adding a new tool. OTel's own `gen_ai.*` semantic conventions
(already defined, designed for exactly this — model name, token counts,
latency) attach to spans around each LLM call and each retrieval call; a
custom `rag_citation_grounded` span attribute records §2.6's deterministic
citation check's own result at request time too, not just in CI — a live
per-request signal in Grafana on top of the CI gate's aggregate one (the
heavier RAGAS/DeepEval metrics stay CI-only, not run per live request —
they're too slow/costly to run inline on every demo query). No new
observability tool (Langfuse/Phoenix/etc.) — matches the project's
self-hosted, $0-by-default posture, and the roadmap's own explicit "the
general layer doesn't get replaced by the AI-specific one" framing: same
stack, more attributes.

**Stated caveat**: OTel's `gen_ai.*` conventions are real and the right
direction (OTel itself graduated CNCF in 2026, and major observability
vendors are adopting them), but they remain experimental/pre-1.0 as of
this year — attribute names can still shift upstream. Verify the current
spec at implementation time rather than treating the names above as
final, the same "pin at implementation time" treatment already given to
Ollama model tags (§2.9).

### 2.9 Stated defaults (not forks — recorded for completeness)

- **Ollama models** (local/default runtime): exact generation + embedding
  model tags pinned at implementation time against Ollama's then-current
  library, not hardcoded in this doc — model catalogs move faster than a
  design doc's shelf life.
- **`ai/` directory layout**: already fixed by the roadmap doc's repo-
  layout section (`ai/policy-intelligence/`, `ai/analytics-copilot/`,
  `ai/dashboard-assist/`) — followed as-is, not reopened here.
- **Threat-model boundary** (policy corpus trusted, applicant-submitted
  content untrusted): already decided in roadmap §3.3; §2.2 above is its
  application to this specific feature, not a new decision.

### 2.10 Cross-cutting AI architecture & safety patterns

Found during a systematic pass for missing standard patterns, after §2.1-
2.9 were otherwise settled — applies across every feature above rather
than to one:

- **Bounded copilots, not autonomous agents.** Every AI capability in this
  phase is a fixed, short pipeline — retrieve→generate, or NL→tool-
  call→execute — never an open-ended agent that plans and loops over its
  own tool calls. This is a deliberate architectural stance, not an
  omission: a fixed pipeline is auditable end to end and easy to keep on
  the "assists" side of the governing principle; a self-directed multi-
  step agent is a fundamentally harder thing to bound, log, and review
  before anything binding happens. If a real need for multi-step planning
  ever emerges in a later phase, that's a new brainstorm, not a default.
- **Structured output, not free text.** Every place an LLM's output
  becomes something else's input — the rule-authoring copilot's proposed
  parameter diff (§2.3), the Analytics Copilot's MCP tool-call arguments
  (§2.4), the dashboard-authoring assist's proposed spec (§2.5) — is
  schema-validated (Pydantic v2, this project's existing standard per
  CLAUDE.md's Python conventions) before it's rendered as a diff or
  executed as a call. An LLM response that fails validation is a rejected
  draft, never a partially-applied one.
- **Input/output guardrails on the one public, unauthenticated surface.**
  The public demo (§2.7) is the sole capability in this phase reachable
  without an account — it gets a moderation/safety filter on both the
  incoming question (blocking prompt-injection and off-topic-abuse
  attempts) and the generated answer, on top of the trusted/untrusted
  content boundary §2.2 already established. Two reasons, not one:
  protects the demo's own integrity for a real visitor, and protects the
  OpenRouter free-tier account itself from being used for unrelated
  abuse, which risks losing free-tier access entirely — a second, very
  concrete reason this isn't optional for the one internet-facing piece.
- **Tiered circuit breaker**, naming what §2.7 already described: three
  tiers, not a single on/off switch — free-tier OpenRouter, then a
  capped paid-tier fallback, then a clearly-stated "temporarily
  unavailable" response once both are exhausted (or on an upstream
  outage). Each transition is silent to the user except the final one;
  nothing surfaces a raw error or hangs at any tier.
- **No PII exposure risk in the Analytics Copilot**, inherited rather
  than newly built: gold marts are already PII-free (Phase 1b Task 5's
  `no_pii_in_gold` test), so `canopica_analytics_ro` (§2.4) structurally cannot
  return anything requiring detokenization — worth stating explicitly
  rather than leaving a reader to wonder whether this was considered.
- **Considered, deliberately deferred** (stated rather than silently
  absent, per this project's own convention): query rewriting/expansion
  ahead of retrieval (most target questions are single-shot factual policy
  lookups where the raw question is already a reasonable retrieval query;
  add only if real usage shows otherwise — not built for a failure mode
  not yet observed) and a structured feedback loop (thumbs-up/down on
  Policy Q&A answers feeding future golden-set curation) — a real, common
  production pattern, but additive scope for a later phase, not this one.

## 3. Tradeoffs doc — refinements this unlocks

- Add a row to the AI/Platform tier: **Public-demo inference** | Local
  default: Ollama, $0 | Public demo: OpenRouter free-tier models, falling
  back to a cheap paid OpenRouter model under a $5/mo hard cap | `~` |
  Free/cheap-tier models are lower-quality and less consistently available
  than a paid frontier model a real production system would use — a real
  fidelity gap, not just a same-shape swap.
- Note under §4 ("what this costs"): the demo only fails closed to
  "unavailable" once *both* the free tier and the $5/mo paid-fallback
  budget are exhausted — a real visitor sees degraded model quality (the
  paid-fallback model, likely still a small/cheap one, not a frontier
  model) before they'd ever see "unavailable," and only sees
  "unavailable" at all in a genuinely high-traffic month. State the
  actual three-tier shape plainly rather than implying either "always
  free" or "always available."
- Add `canopica_analytics_ro` to the Secrets/Authorization tier as a concrete
  instance of the least-privilege pattern already established by
  `canopica_app` — not a new pattern, an extension of one already in place.

## 4. What this doc does not settle

Exact Ollama model tags, the golden-question set's exact wording/count
beyond "~20," the exact free-host provider for the demo app + OpenSearch,
RAGAS/DeepEval's exact baseline-relative threshold values, and the
specific reranker model are Task-level implementation details, decided
when that task is actually written, not phase-level forks. Document Intake,
Correspondence, Fraud Triage, Compliance/SLA, and SOP Copilot are Phase 3
and Phase 4 — out of this doc's scope entirely; each gets its own design
pass when its phase begins, per this project's own stated convention.

The implementation plan — file-by-file, task-by-task, mirroring
`docs/plans/2026-08-22-phase-1b-implementation-plan.md`'s shape — is the
next step once this doc is reviewed and approved.

## 5. AI design pattern catalog (summary)

Every named pattern this doc uses, in one place, for a reader who wants
the list without reading §2 end to end.

| Pattern | Where | Why chosen |
|---|---|---|
| Hybrid retrieval (lexical + vector) | §2.1 | Keyword precision for exact terms plus semantic recall for paraphrase — the 2026 production baseline for RAG, not an optional upgrade. |
| Reciprocal Rank Fusion (RRF) | §2.1 | Fuses two retrieval methods by rank, not raw score — BM25 and cosine-similarity scores aren't on comparable scales, so naive averaging is a known failure mode. |
| Reranking (cross-encoder) | §2.1 | A second, precise relevance pass after broad retrieval — real, material accuracy gains over hybrid-only, and OpenSearch already supports it natively. |
| Structure-aware chunking | §2.1 | Chunks at the source document's own citation-grade boundaries (CFR subsections), not a fixed token window — citations stay independently verifiable. |
| RAG answer provenance/versioning | §2.1, §2.2 | Regulated-domain RAG best practice, and the same reproducibility discipline this project already applies to determinations — a Policy Q&A answer shouldn't be the one unreconstructible thing in the system. |
| Grounding / abstention | §2.2 | Says "insufficient information" instead of guessing when retrieval finds nothing relevant — the standard fix for RAG's most common hallucination path. |
| Trusted/untrusted content boundary | §2.2 (roadmap §3.3) | Retrieved policy text and DMN trace values are trusted context; nothing applicant-submitted shares that channel — the standard RAG prompt-injection boundary. |
| Human-in-the-loop review before publish | §2.3, §2.5 | Every AI-proposed change (a parameter version, a dashboard spec) is a diff a human accepts or rejects — never auto-applied. Directly implements the governing principle, not just consistent with it. |
| Governed semantic layer, not text-to-SQL | §2.4 | An LLM never generates raw SQL against physical tables; it selects from a compiled, tested metric manifest. 2026 benchmark data shows this closes most of the text-to-SQL accuracy gap on its own. |
| Tool-calling over MCP | §2.4 | The standard 2026 mechanism for exposing a governed API (here, MetricFlow's metrics) to an LLM as callable, schema-validated tools, instead of prose stuffed into a prompt. |
| Authorization before query compilation | §2.4 | What a caller's tool list even contains is resolved from their role before a query is built — catches what a query-time-only check can only catch after the fact. |
| Bounded copilots, not autonomous agents | §2.10 | Every capability is a fixed, auditable pipeline, never a self-directed multi-step agent — a deliberate scope boundary that makes the governing principle enforceable by construction. |
| Structured output (schema-validated) | §2.10 | Every LLM output that becomes another system's input is Pydantic-validated before use — a malformed response is a rejected draft, never a partially-applied one. |
| Input/output guardrails | §2.10 | The one unauthenticated public surface gets a moderation filter on both directions — protects the demo and the free-tier account it depends on. |
| Tiered circuit breaker | §2.7, §2.10 | Free-tier model → capped paid-model fallback → clear "unavailable," never a raw error — real availability exactly when free-tier limits are most likely to bite, for a fully bounded cost. |
| RAGAS metrics + DeepEval CI gating | §2.6 | The defined 2026 standard for RAG evaluation, with baseline-relative thresholds so an LLM-judged metric can still gate CI without flaking on ordinary noise. |
| Deterministic citation pre-check | §2.6, §2.8 | A cheap, zero-noise check layered under the LLM-judged metrics — catches a literally-fabricated citation ID before spending a judge call on it. |
| OTel `gen_ai.*` semantic conventions | §2.8 | Extends the observability stack this project already built (Phase 1b Task 9) rather than adding a second tool — same instrumentation standard the wider industry is consolidating on. |
| Least-privilege execution roles | §2.4 (roadmap §3.3) | `canopica_analytics_ro` mirrors `canopica_app`'s own pattern from Phase 1a — a new capability gets the narrowest role that can do its job, not the app's existing read-write one. |
