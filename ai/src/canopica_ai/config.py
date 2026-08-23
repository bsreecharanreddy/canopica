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

    cfr_corpus_index: str = "cfr-part-273"
    cfr_search_pipeline: str = "cfr-hybrid-rerank"
    embedding_dimension: int = 768

    # Relative to cwd, not the repo root: every entry point here runs via
    # `uv run` from inside ai/ (see the Makefile), matching data-platform's
    # own warehouse_root convention.
    corpus_raw_dir: Path = Path("src/canopica_ai/policy_intelligence/corpus/raw")
