"""Runtime configuration for the Canopica AI capability layer."""

from pathlib import Path

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
    # sharing a host with OpenSearch/Keycloak/portal-api: successful calls
    # took 1m10s-1m44s, and a 120s timeout actually cut one off at exactly
    # 2m0s (Ollama logged it as a 500 once the client gave up). Keeps real
    # headroom above the observed worst case rather than being a guessed
    # round number.
    ollama_timeout_seconds: float = 240.0

    cfr_corpus_index: str = "cfr-part-273"
    cfr_search_pipeline: str = "cfr-hybrid-rerank"
    embedding_dimension: int = 768

    # Same shared Postgres canopica_data.config.Settings already writes to (e.g.
    # the pii_token vault) -- ai.policy_qa_answer reuses that instance
    # rather than standing up a second database, per design doc §2.2.
    operational_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"

    # Portal API's own base URL -- answer_denial() forwards the citizen's
    # bearer token here to read their own determination trace server-side.
    portal_api_url: str = "http://localhost:8080"

    # Relative to cwd, not the repo root: every entry point here runs via
    # `uv run` from inside ai/ (see the Makefile), matching data-platform's
    # own warehouse_root convention.
    corpus_raw_dir: Path = Path("src/canopica_ai/policy_intelligence/corpus/raw")

    # Analytics Copilot (Phase 2 Task 5). Same JWKS/issuer URIs
    # portal-api's own SecurityConfig.java validates against (application.yml,
    # env vars CANOPICA_KEYCLOAK_WORKERS_*) -- this service is its own resource
    # server, not routed through the portal, so it fetches and verifies
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

    # Dashboard-authoring copilot (Phase 2 Task 6). The TMDL files are this
    # service's only source of truth for what tables/columns/measures
    # already exist -- read-only, same sibling-project relative-path
    # convention as data_platform_dbt_project_dir above.
    reporting_semantic_model_dir: Path = Path("../reporting/semantic-model")
