"""Runtime configuration for the Canopica AI capability layer."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings shared by every ``ai/`` entry point.

    Every value has a local-development default so a fresh clone runs without
    a ``.env`` file; the Compose stack overrides them with ``CANOPICA_``-prefixed
    environment variables, matching ``canopica_data.config.Settings``'s own
    pattern.
    """

    model_config = SettingsConfigDict(env_prefix="CANOPICA_", env_file=".env", extra="ignore")

    opensearch_url: str = "http://localhost:9200"
    ollama_base_url: str = "http://localhost:11434"

    # Pinned at implementation time (CLAUDE.md/plan convention: every
    # image tag and model tag in this repo is pinned, not left floating).
    # nomic-embed-text produces 768-dim embeddings, matching
    # infra/opensearch/cfr_index_mapping.json's knn_vector dimension.
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_generation_model: str = "llama3.2:3b"

    # Generation knobs, settings-driven so CI and a real deployment can tune
    # them without a code change. All three were set from live measurement
    # (2026-08-23) against this repo's own corpus and questions, not picked
    # as round numbers:
    #   temperature -- Ollama's own default is 0.8, which for a *grounded*
    #     policy answer is actively wrong: the same question produced 115
    #     vs 294 tokens across two runs, and on one of three real questions
    #     the model returned a 20-token non-answer citing nothing at all,
    #     which costs a whole extra retry generation (see service.py's
    #     grounding retry) or an abstention. At 0.2 every one of the same
    #     three questions cited real sections.
    #   num_predict -- Ollama defaults to unbounded. Real answers measured
    #     at 47-73 tokens, so this is a backstop against a pathological
    #     runaway answer, deliberately not the mechanism that keeps answers
    #     short (the prompt's own brevity instruction is). A cap tight
    #     enough to truncate normal answers would cut them mid-sentence.
    #   keep_alive -- deliberately left at Ollama's own 5m default rather
    #     than extended. A longer window was tried (10m, to avoid a
    #     measured 14.9s cold load) and reverted: it buys nothing here,
    #     because this suite's generation calls run back to back and keep
    #     the model warm well inside 5m anyway, while keeping the
    #     embedding model resident alongside it for longer on a host that
    #     is already memory-tight -- and a llama-server killed by the OOM
    #     killer mid-suite (observed live, `signal: killed`) surfaces as an
    #     uncited answer, which the grounding retry then turns into a
    #     spurious abstention. Exposed as a setting so a real deployment
    #     with headroom can raise it; the default just doesn't spend
    #     memory this project's own hosts don't have.
    ollama_temperature: float = 0.2
    ollama_num_predict: int = 512
    ollama_keep_alive: str = "5m"

    # Set explicitly rather than left to the model default, because the
    # default is 2048 and this system's real prompts do not fit in it.
    # Measured (2026-08-23) against the live stack: the rule-authoring
    # prompt for the real 39-parameter FY2026 set plus an 8,000-character
    # excerpt is 12,186 characters, and Ollama reported `prompt_eval_count`
    # of 1,026 at num_ctx=2048 versus 3,105 at 4,096 -- it discarded two
    # thirds of the prompt and still answered 200 OK. The parameter list is
    # at the front of that prompt, so the model would have been diffing
    # against a list it never saw. Task 2's denial prompt was measured at
    # 1,849 tokens against the same 2,048 ceiling, close enough that a
    # slightly longer retrieval would have started truncating there too.
    # Costs roughly 235MB more KV cache than 2048, which is real on a
    # memory-tight host and is the right trade against silent truncation.
    ollama_num_ctx: int = 4096

    # Empirically measured (2026-08-23) against real CPU-bound generation
    # sharing a host with OpenSearch/Keycloak/api: successful calls
    # took 1m10s-1m44s, and a 120s timeout actually cut one off at exactly
    # 2m0s (Ollama logged it as a 500 once the client gave up). That
    # measurement's prompts were not this project's largest, though:
    # raised 240 -> 480 (2026-08-25) after Task 7's eval-suite gate hit a
    # real httpx.ReadTimeout at 240s **independently on two hosts** --
    # this dev machine under load, and the actual GitHub Actions CI
    # runner on an otherwise-clean job -- both against golden_set.yaml
    # questions whose assembled prompt runs up to ~15,500 characters
    # (several large retrieved CFR chunks together), well past the
    # ~12,186-character prompt the original 240s figure was measured
    # against. CPU-bound prompt evaluation cost scales with token count,
    # so a real number over the new, larger worst case beats guessing a
    # smaller "should be enough" bump.
    ollama_timeout_seconds: float = 480.0

    # Same Jaeger the API and the data pipeline already export to
    # (infra/docker-compose.yml's `jaeger` service), and the same variable
    # name canopica_data.config.Settings uses, so one env var configures both.
    # The default is the *published* host port rather than a container
    # address because `ai/` has no Compose service of its own -- every
    # entry point here runs on the host via `uv run`.
    otel_exporter_endpoint: str = "http://localhost:4318/v1/traces"

    # `ai-eval`'s CI job runs run_eval.py for real against every traced
    # call site (hybrid_search, answer_general) but never starts Jaeger --
    # ci.yml deliberately keeps that job to just opensearch+ollama to
    # protect its own tight wall-clock budget. Confirmed live (CI run
    # 32803875411): with tracing on, every span close blocked several
    # seconds retrying against the refused connection, dozens of times
    # over a run. That job sets CANOPICA_OTEL_ENABLED=false; every other
    # environment (local dev, the e2e-ai job, a real deployment) has a
    # real Jaeger and leaves this at its default.
    otel_enabled: bool = True

    cfr_corpus_index: str = "cfr-part-273"
    cfr_search_pipeline: str = "cfr-hybrid-rerank"
    embedding_dimension: int = 768

    # Caseworker SOP Copilot (Phase 4 Task 7, design doc §2.5): a separate
    # index so SOP and policy retrieval never cross-contaminate, but the
    # *same* cfr_search_pipeline above -- a search pipeline is a named,
    # cluster-level set of processors (RRF fusion + cross-encoder rerank),
    # invoked per-request via a query param, not bound to one index at
    # creation, so reusing it here means Task 7 doesn't need a second
    # ml-commons model deployment doubling the JVM-heap circuit-breaker
    # risk search_pipeline.py's own extensive comments already document
    # fighting once.
    sop_corpus_index: str = "canopica-sop"

    # Same shared Postgres canopica_data.config.Settings already writes to (e.g.
    # the pii_token vault) -- ai.policy_qa_answer reuses that instance
    # rather than standing up a second database, per design doc §2.2.
    operational_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"

    # Document Intake (Phase 3 Task 3): same MinIO instance and credentials
    # api/src/main/resources/application.yml's own canopica.minio.* block
    # defaults to -- one bucket, one set of dev credentials, read by both
    # languages rather than each defining its own.
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "canopica"
    minio_secret_key: str = "canopica-minio-dev"
    minio_bucket: str = "canopica-documents"

    # API's own base URL -- answer_denial() forwards the citizen's
    # bearer token here to read their own determination trace server-side.
    api_url: str = "http://localhost:8080"

    # Relative to cwd, not the repo root: every entry point here runs via
    # `uv run` from inside ai/ (see the Makefile), matching data-platform's
    # own warehouse_root convention.
    corpus_raw_dir: Path = Path("src/canopica_ai/policy_intelligence/corpus/raw")

    # Analytics Copilot (Phase 2 Task 5). Same JWKS/issuer URIs
    # api's own SecurityConfig.java validates against (application.yml,
    # env vars CANOPICA_KEYCLOAK_WORKERS_*) -- this service is its own resource
    # server, not routed through the API, so it fetches and verifies
    # signing keys independently rather than trusting a forwarded identity.
    keycloak_workers_jwks_uri: str = (
        "http://localhost:8081/realms/canopica-workers/protocol/openid-connect/certs"
    )
    keycloak_workers_issuer_uri: str = "http://localhost:8081/realms/canopica-workers"

    # Sibling project, not a dependency: MetricFlow binds semantic models to
    # dbt's own compiled manifest (design doc 2026-08-24-analytics-semantic-
    # layer-execution-and-authorization.md), and that manifest is
    # data-platform's own build artifact -- ai/ reads it via data-platform's
    # already-built `mf` binary rather than re-vendoring dbt-metricflow's
    # heavy dependency stack a second time. A real production split would
    # expose this as its own queryable service rather than a monorepo-local
    # path assumption; recorded here rather than hidden as a magic default.
    data_platform_dbt_project_dir: Path = Path("../data-platform/dbt/canopica_warehouse")
    mf_binary_path: Path = Path("../data-platform/.venv/bin/mf")
    duckdb_path: Path = Path("../data-platform/warehouse/canopica.duckdb")

    # Data-quality anomaly detection (Phase 4 Task 9). Same serving Postgres
    # canopica_data.config.Settings.serving_dsn already writes reporting.*
    # gold-mart copies into -- reporting.data_quality_incident is data-
    # platform-owned serving-layer state (design doc §2.8), so this reuses
    # that instance rather than standing up a second database.
    serving_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_serving"

    # Dashboard-authoring copilot (Phase 2 Task 6). The TMDL files are this
    # service's only source of truth for what tables/columns/measures
    # already exist -- read-only, same sibling-project relative-path
    # convention as data_platform_dbt_project_dir above.
    reporting_semantic_model_dir: Path = Path("../reporting/semantic-model")

    # Eval-suite CI gate (Phase 2 Task 7) judge model -- OpenRouter, not
    # local Ollama. Measured live (2026-08-24): the local llama3.2:3b
    # judge was both too slow (minutes per DeepEval/RAGAS metric call) and
    # outright unreliable (one call exceeded a 240s timeout and crashed
    # the run) for a CI-blocking gate. A judge never serves user traffic
    # -- it's a bounded, CI-only step -- so this repo's "self-hosted, $0"
    # requirement for the *generation* model under test (unchanged, still
    # local) doesn't carry over to it.
    #
    # Moved off OpenRouter's `:free` tier entirely on 2026-08-26 -- not
    # from a hunch, from two consecutive real full-length eval runs
    # (2026-08-24, and *two more* the same night as this comment) each
    # losing 45-55 minutes of already-correct work to a free-tier judge
    # failure in its last few seconds: a 200-wrapped upstream 502 twice,
    # a real 404, and a 200 response that silently wasn't loadable JSON
    # despite a strict schema. Widening the retry window (judge_model.py)
    # did not fix the two same-night failures -- free capacity for this
    # specific `:free` model was genuinely unavailable long enough to
    # exhaust 5 attempts across ~30s, not just unlucky once. `is_free_tier:
    # false` on this project's own OpenRouter account (paid credits
    # already provisioned, see STATUS.md) meant paid routing needed no new
    # setup -- just a model string.
    #
    # `deepseek/deepseek-chat` (DeepSeek V3), not `anthropic/claude-
    # haiku-4.5` (tried first, live-verified working, both structured-
    # output compliance and pricing checked against OpenRouter's own API
    # before committing to either): DeepSeek's $0.2574/$1.029 per-MTok
    # rate (OpenRouter's own pricing, live-checked) is the cheapest of
    # four real candidates compared the same way (GPT-5 Mini $0.25/$2.00,
    # Gemini 2.5 Flash $0.30/$2.50, Claude Haiku $1/$5) -- input price is
    # what matters most for this workload specifically, since a judge
    # call's context (retrieved chunks + generated answer) dwarfs its
    # short structured verdict, and DeepSeek's input rate is the lowest
    # of the four. Verified live against the *exact* `response_format:
    # json_schema` + `strict: true` shape DeepEval sends -- the identical
    # request that produced the free-tier NVIDIA model's silent-invalid-
    # JSON failure earlier tonight -- before committing, not assumed
    # compatible from the pricing page alone.
    #
    # Kept on OpenRouter rather than moved to a direct provider key: zero
    # new code either way (judge_model.py's client already speaks
    # OpenRouter's protocol generically), so switching *which* paid model
    # sits behind it is a one-line change, not a new integration -- the
    # exact flexibility a provider-agnostic client is supposed to buy.
    # `anthropic/claude-haiku-4.5` stays a proven, working fallback if
    # DeepSeek's paid tier ever shows the same class of problem the free
    # tier did; a direct (non-OpenRouter) integration for either provider
    # remains real, separately-scoped follow-up work, not required to get
    # off the unreliable free tier tonight -- see
    # `docs/design/2026-08-26-anthropic-tiered-inference-provider.md`.
    openrouter_api_key: str | None = None
    openrouter_judge_model: str = "deepseek/deepseek-chat"
    openrouter_timeout_seconds: float = 120.0

    # Task 9 (public demo). `inference_mode` selects which `LlmClient`
    # `answer_general()`'s caller constructs -- `OllamaClient` for `local`
    # (unchanged, still what the authenticated app and every ai-eval/
    # e2e-ai test exercise), `OpenRouterTieredClient` for `public_demo`.
    inference_mode: Literal["local", "public_demo"] = "local"

    # Free tier, live-verified working (2026-08-24, the same probe that
    # ruled out OpenRouter's free auto-router and a safety-classifier
    # false pick -- judge_model.py's module docstring): a plain chat call
    # and a `response_format: json_schema` structured call both succeeded
    # cleanly against this exact model.
    openrouter_public_demo_free_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"

    # Paid tier, staged in two steps (docs/STATUS.md's "Public demo
    # inference" row, decided 2026-08-26): `deepseek/deepseek-chat` for
    # the rest of active development -- cheapest of four real candidates
    # on OpenRouter's own live pricing, and already proven as the eval
    # judge above -- repointed to `anthropic/claude-haiku-4.5` in the same
    # commit as the public-repo flip, for a spec-clean
    # `gen_ai.provider.name` value and to avoid a China-based model
    # answering the public-facing surface. The price-per-MTok pair below
    # MUST move with the model -- nothing here reads a live price from
    # OpenRouter, so the swap is three lines, not one.
    openrouter_public_demo_paid_model: str = "deepseek/deepseek-chat"
    openrouter_public_demo_paid_input_price_per_mtok_usd: float = 0.2574
    openrouter_public_demo_paid_output_price_per_mtok_usd: float = 1.029

    # A hard ceiling on the paid tier's cumulative spend for the current
    # calendar month, per design doc §2.7 -- once at or over this, the
    # client stops falling back to paid on a free-tier rate limit rather
    # than continuing to spend. $5 is deliberately generous against this
    # project's real demo-scale traffic (a single question costs
    # fractions of a cent at either pinned model's rate).
    openrouter_public_demo_monthly_cap_usd: float = 5.0

    # "A simple counter, persisted -- a file or a Postgres row is enough
    # for this scale, not a metering service" (Task 9 plan Step 1).
    # Relative to `ai/`'s own cwd, matching this file's other local-data
    # paths (`duckdb_path` etc.) -- Step 5's Fly.io deploy mounts a small
    # persistent volume at this path so it survives a restart.
    openrouter_public_demo_spend_file: Path = Path("data/public_demo_spend.json")

    # Task 9 Step 3's per-session daily cap (design doc §2.10's "app-level
    # rate limiter"), in front of the whole tiered chain -- UX/anti-abuse,
    # not cost control (the $5/mo spend cap above already bounds real
    # cost: at either pinned model's rate this limit would need to be in
    # the thousands before it mattered for spend). 20 is a deliberately
    # generous round number for a demo visitor genuinely trying it out,
    # not a measured figure -- there's no real traffic yet to measure
    # against, unlike this file's other settings.
    public_demo_daily_request_limit_per_session: int = 20
