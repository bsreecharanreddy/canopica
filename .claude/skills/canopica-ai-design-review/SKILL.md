---
name: canopica-ai-design-review
description: Use during the brainstorm step of any Canopica design decision that touches an AI/LLM capability (RAG, a copilot, an agent, an eval gate, AI observability) — a live-research pass against current industry-standard AI design patterns before the design doc is finalized.
---

# Canopica AI design review

`canopica-design-decision`'s brainstorm step already asks for a recommendation
and the main tradeoff. For an AI/LLM capability specifically, that's not
enough on its own: this area moves fast enough that a reasonable-sounding
architecture drafted from memory can already be behind — as this project's
own Phase 2 design doc found in one pass (retrieval fusion method, RAG
provenance, the standard LLM↔semantic-layer integration shape, eval-gating
method, and an observability-spec caveat all changed after checking). This
skill is that check. It runs *inside* `canopica-design-decision`'s workflow,
not instead of it.

## 1. Trigger: any design decision touching an AI/LLM capability

Retrieval, a copilot or agent, an eval/gating mechanism, AI-specific
observability, or a public-facing AI surface. A decision that's AI-
adjacent but not AI-itself (e.g., which Postgres role a service uses)
doesn't need this pass — `canopica-design-decision`'s own workflow covers it.

## 2. Check each relevant category via live research, not memory

Search dated to the current year — training data on fast-moving AI
practice goes stale faster than most other domains this project makes
decisions in. Categories, check only the ones the decision actually
touches:

- **Retrieval** — hybrid search fusion method (not just "hybrid"), 
  reranking, chunking strategy, provenance/versioning of what was
  retrieved.
- **Agent/copilot boundary** — bounded pipeline vs. autonomous multi-step
  agent; if tool-calling, the standard integration mechanism (e.g., MCP)
  rather than a bespoke one.
- **Structured output** — is the LLM's output schema-validated before
  another system consumes it, or is it free text being parsed hopefully.
- **Grounding/abstention** — does the design say "insufficient
  information" when retrieval/context is weak, or does it always attempt
  an answer.
- **Evaluation** — the current standard metric set and tooling for this
  kind of capability, and whether the gating mechanism can actually block
  CI without flaking (deterministic checks vs. baseline-relative
  LLM-judge thresholds, not a blanket "no LLM judges in CI").
- **Observability** — current semantic-convention/schema status for
  whatever's being instrumented; note explicitly if it's still
  experimental/pre-1.0 rather than presenting it as settled.
- **Safety/guardrails** — input/output filtering, least-privilege
  execution, and — specifically for anything public-facing/unauthenticated
  — moderation and abuse protection, including protecting any free/cheap
  API tier the design depends on from being exhausted by abuse.
- **Cost/reliability** — rate limiting, circuit-breaker/graceful-
  degradation behavior, spend caps.

## 3. Note what changed inline, cite sources, don't silently fold it in

State plainly that the doc was checked against current practice and list
what actually changed as a result — the same way Phase 2's design doc
does in its own opening section. Presenting a researched revision as if
it were the original brainstorm's own idea erases exactly the information
a future reader most needs: which parts of this design are load-bearing
because of a real citation, versus a judgment call made from priors.

## 4. Recording is `canopica-design-decision`'s own step 3 — don't duplicate it

Once approved, the decision (and which pattern led to it) gets recorded
the normal way: the design doc itself, the tradeoffs doc if it substitutes
for a real production choice, and `docs/STATUS.md`'s decisions table. This
skill's job ends at "checked and revised" — it doesn't add a fourth
recording location.

## 5. For a new AI-capability doc, close with a pattern catalog

A table — pattern, where it's used, why it was chosen — the same shape as
Phase 2's design doc's own closing section. Makes the doc a real reference
for "what patterns does this system use and why," not just a decision log
a reader has to reconstruct that answer from.
