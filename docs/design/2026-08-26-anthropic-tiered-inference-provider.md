# Canopica — Does a hosted Claude tier belong in the inference chain, and where

Status: **superseded** — kept as a record of how the design evolved, not
as current guidance
Date: 2026-08-26
Superseded by: `docs/STATUS.md`'s "Public demo inference" row (Decisions
already made)

> **Read that STATUS.md row, not this doc's §4 recommendation.** Later
> the same day, DeepSeek's live-proven reliability as the eval judge (see
> that row) made a second full provider integration unnecessary for the
> problem this doc set out to solve (OpenRouter free-tier flakiness).
> Settled instead: `deepseek/deepseek-chat` for the rest of active
> development, `anthropic/claude-haiku-4.5` from the public-repo flip
> onward — both through the same `OpenRouterTieredClient`, so it's a
> one-line config value, not the new-provider decision this doc explored.
> §§1-3's research (pricing, 2026 hybrid-routing practice, the
> `gen_ai.provider.name` spec point) still hold and informed that
> decision; only §4's specific recommendation (add Claude as a distinct
> provider) didn't survive contact with same-day evidence.

## 1. Why this exists

Surfaced during a CI firefighting session (2026-08-26), not from a
roadmap gap: the shared self-hosted runner VM spent the night hitting
memory pressure and a noisy eval-gate faithfulness score, both traceable
to CPU-only local Ollama generation (`llama3.2:3b`, no GPU, ~2-3 minutes
per real question — see that date's STATUS.md verification-log rows).
The question this raised — "should Canopica stop self-hosting generation
and use a hosted Claude model instead" — sounds like it reopens
`docs/design/2026-08-23-phase-2-policy-intelligence-analytics-ai-design.md`
§2.9's stated default (self-hosted Ollama, $0). **It mostly doesn't.**
That same design doc's §2.7 and its implementation plan's Task 9
(`docs/plans/2026-08-23-phase-2-implementation-plan.md:960-1030`,
`[ ]`, not yet built) already approved a *second*, hosted-tiered
`LlmClient` implementation — `OpenRouterTieredClient` — selected by
`Settings().inference_mode` (`local` | `public_demo`), scoped
specifically to the public, unauthenticated demo surface, never to the
main authenticated app. `ai/src/canopica_ai/common/llm_client.py`'s own
module docstring already names this: "Task 9 can add a second
implementation behind the same interface without touching any [existing
call site]." The provider-agnostic architecture is not new. The
open question is narrower: **should Claude be that second provider (or
join it), and does the scope stay exactly what Task 9 already specified
— `public_demo` only?**

Two things happened tonight that bear directly on that narrower
question, both real incidents, not hypotheticals:

- **Real, current Claude API pricing was checked live** (not assumed):
  Haiku 4.5 at $1/$5 per MTok in/out, Sonnet 5 at $2/$10. A Policy Q&A
  call (a few retrieved CFR chunks + question in, a short grounded
  answer out — roughly 2,000 input / 300 output tokens) costs
  **~$0.0035 (Haiku) to $0.007 (Sonnet) per question**. Trivial at this
  project's actual traffic scale, and well under the $5/mo cap §2.7
  already approved for OpenRouter's paid-fallback tier.
- **This project has now hit three distinct real failure shapes on
  OpenRouter's free-tier hosted routing** — the exact pattern §2.7's
  `OpenRouterTieredClient` leans on as its *primary* (not fallback)
  tier — all against the eval-gate's judge model, all documented in
  `judge_model.py`'s own comments: a 200-wrapped upstream 502 "Service
  temporarily overloaded" (2026-08-24), a transient 404 on a listed,
  working model (2026-08-25), and a 200 response that silently wasn't
  loadable JSON despite a strict schema being sent (2026-08-26, this
  same session). All three were fixed with retries, not architecture
  changes — but three independently-discovered reliability gaps in one
  week, all on the same "free-tier hosted routing" pattern, is real
  operational history the original §2.7 tradeoff didn't have when it was
  written.

## 2. Checked against current practice

Per `canopica-ai-design-review`, checked by live research rather than
drafted from memory, since this touches an AI capability's provider
boundary.

**Confirmed — a hybrid, provider-routed architecture is the 2026
consensus, not a self-hosted-vs-hosted binary.** Current guidance:
"the right answer for most teams in 2026 is a deliberate hybrid
architecture that routes each request to the most cost-effective and
appropriate inference backend based on volume, quality requirements,
privacy constraints, and latency needs... run a self-hosted instance for
high-volume, predictable workloads (embeddings, classification,
summary, retrieval rewrites), and route long-tail or peak-load requests
to a hosted API" ([Effloow, *Self-Hosting LLMs vs Cloud APIs:
2026*](https://effloow.com/articles/self-hosting-llms-vs-cloud-apis-cost-performance-privacy-2026)).
This maps cleanly onto Canopica's actual split: `nomic-embed-text`
(embeddings — high-frequency, every retrieval, cheap and fast locally)
stays self-hosted under this guidance without needing to reopen
anything; generation (low-volume per request, quality- and
latency-sensitive) is exactly the workload class the same guidance says
to route to a hosted API. `LlmClient`'s existing protocol boundary
already sits at exactly the right seam for this — it was not designed
with this research in mind, but it matches it.

**Confirmed, and it changes what "the free tradeoff" actually means at
this scale.** "Cost crossover vs frontier APIs lands around 2M-5M
tokens/day on reserved GPU capacity over a 12-month window, and below
that, the API still wins" (same source). Canopica's real and realistic
demo traffic is nowhere near that floor. This means §2.9's "self-hosted,
$0" default is not, and was never claimed to be, the objectively
cheaper or faster engineering choice at this project's scale — self-
hosting a 3B model on a CPU-only VM is slower (2-3 min/question,
measured) *and* not meaningfully cheaper than a hosted API once VM time
is counted, only $0-*marginal*-cost per call. That's worth stating
plainly rather than leaving it implied: the self-hosted default is a
**deliberate portfolio-narrative choice** (demonstrating a working,
zero-external-dependency, fully self-hostable AI layer — genuinely
valuable for the stated audience, per `user_career_goals_and_disposition`
and `feedback_code_quality_and_tech_currency`), not a technical win on
cost or latency. Keeping it as the *stated default* while adding a real,
working, measured hosted alternative is honest about that; quietly
treating "self-hosted" as also "objectively better" would not be.

**One concrete implementation detail confirmed, not left to guess at
implementation time.** §2.8's own stated caveat says to verify OTel's
`gen_ai.*` conventions live rather than trust a design doc's prose.
Done: `gen_ai.provider.name` MUST be `"anthropic"` for Claude calls — a
real, spec-listed enum value ([OpenTelemetry, *Semantic conventions for
Anthropic client
operations*](https://opentelemetry.io/docs/specs/semconv/gen-ai/anthropic/)),
unlike Ollama's own `"ollama"` value, which Phase 2 Task 8's own
verification log records as a *deliberate off-enum* choice (no real
value exists for it in the spec). A Claude implementation would be the
first provider in this codebase's observability that maps onto the
spec cleanly rather than around it — a small point, but a real one for
`common/observability.py`'s `traced_llm_call` when this is implemented.

## 3. Options

### Option A — Do nothing now; leave Task 9 exactly as planned (OpenRouter only)

Defers a plausible, cheap reliability improvement — evidenced by three
real incidents this project has already logged against the exact
pattern Task 9 plans to lean on — with no offsetting benefit. Not
recommended, but the honest zero-risk baseline: nothing here blocks
Task 9 from being built exactly as already approved.

### Option B — Replace the main app's self-hosted default with Claude

The deep pivot: `Settings().inference_mode`'s `local` mode itself calls
a hosted Claude client instead of `OllamaClient`, for the authenticated
Policy Q&A path real users and CI both exercise. Would fix tonight's
latency/memory/faithfulness-noise pain directly and fastest.

**Not recommended.** Two real costs, not hypothetical ones: it reverses
§2.9's stated self-hosted default for the *primary* app surface (not
the narrow, already-hosted-tolerant public-demo surface §2.7 scoped),
trading away the demonstrated-capability story for convenience rather
than for a reason tied to the app itself. And it breaks the eval gate's
own reason for existing: `ai-eval`/`e2e-ai` test `answer_general()`,
the exact function real users hit — if CI silently tested a different,
better model than what ships, a red-to-green faithfulness number would
stop meaning "the shipped feature got better" and start meaning
"we changed what we're measuring," undermining Task 7's whole
regression-detection purpose. Doing this for real would need CI
reworked in lockstep, which is exactly the kind of scope this decision
should not be bundled into.

### Option C — Claude joins the `public_demo` tier, exactly where Task 9 already scoped hosted inference (Recommended)

`OpenRouterTieredClient` (or a renamed, provider-generalized
equivalent) gains Claude — Haiku 4.5 by default, given its pricing and
this project's demo-scale traffic — as a tier in the chain Task 9 was
always going to build for `inference_mode=public_demo` only. The
authenticated app's `local` mode, and everything CI's `ai-eval`/`e2e-ai`
jobs test, stays exactly `OllamaClient`, self-hosted, unchanged — this
option touches zero of tonight's CI concerns about eval-gate fidelity,
because it never runs on that path. Real sub-question, deliberately not
resolved by this doc (see §5): does Claude **replace** the free-tier
OpenRouter path entirely, or sit **alongside** it (e.g., as the first
tier, with OpenRouter free-tier demoted to a fallback, or dropped)?
That's an implementation-time call once Task 9 is actually written, not
a today decision — this doc only settles that Claude belongs in the
option set for that one surface.

## 4. Recommendation

**Option C.** It is a narrow extension of already-approved scope
(Task 9, §2.7), not a new architectural decision — the provider-
agnostic seam already exists, already anticipated a second
implementation, and was always going to touch only the one surface
that already tolerates hosted inference. It is justified by this
project's own lived operational history (three real OpenRouter
free-tier failure shapes in one week) rather than by tonight's
unrelated CI pain, which is the honest distinction §1 draws and
this doc holds to: **this does not fix tonight's CI problems, and isn't
meant to** — the VM resize and the eval-gate sample-size fix already in
flight this same session are what's actually unblocking tonight. This
is real, separately-scoped follow-up work for whenever Task 9 gets
built.

## 5. Consequences if adopted

- `docs/design/2026-08-23-phase-2-policy-intelligence-analytics-ai-design.md`
  §2.7 gets a note (not a rewrite — matching how this doc itself amends
  rather than restates it) that Claude is an approved option for the
  tiered chain, alongside or ahead of OpenRouter free-tier, exact shape
  decided at Task 9 implementation time.
- `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`'s
  **Public-demo inference** row (added by the 2026-08-23 doc's §3) needs
  its provider list updated once Task 9 actually implements this; no
  change to its `~` fidelity mark or cost framing — a capped hosted
  tier behind a self-hosted default is the same shape either way.
- `docs/plans/2026-08-23-phase-2-implementation-plan.md`'s Task 9 Step 1
  (`OpenRouterTieredClient`) gets a scope note pointing at this doc when
  Task 9 is actually picked up — the class name and exact tier order are
  implementation-time decisions this doc deliberately leaves open, not
  settled here.
- **Explicitly not touched by this decision**: `local` `inference_mode`,
  `OllamaClient`, the main authenticated Policy Q&A path, or anything
  `ai-eval`/`e2e-ai` currently test. No CI job, eval baseline, or
  `_CI_GATE_QUESTIONS` change follows from this doc.
- **Explicitly left open, for Task 9's own implementation plan, not
  this doc**: whether Claude fully replaces OpenRouter's free tier or
  joins it as an additional/preferred tier; the exact fallback order and
  spend-cap interaction if both providers are live at once; whether the
  $5/mo cap language in §2.7 needs a second, Claude-specific cap or one
  shared ceiling across both hosted providers.
