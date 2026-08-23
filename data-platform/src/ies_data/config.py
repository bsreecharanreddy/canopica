"""Runtime configuration for the IES data platform."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings shared by every data-platform entry point.

    Every value has a local-development default so a fresh clone runs without a
    ``.env`` file; the Compose stack overrides them with ``IES_``-prefixed
    environment variables.
    """

    model_config = SettingsConfigDict(env_prefix="IES_", env_file=".env", extra="ignore")

    # These are fixed placeholder credentials for the local Docker Compose
    # stack only (infra/docker-compose.yml) -- never reachable outside
    # localhost/the Compose network, and overridable via IES_-prefixed env
    # vars (see infra/.env.example). Not production secrets; a real
    # deployment supplies real values through the environment, not this file.
    operational_dsn: str = "postgresql://ies_app:ies_app@localhost:5432/ies_operational"
    serving_dsn: str = "postgresql://ies_app:ies_app@localhost:5432/ies_serving"
    # Relative to cwd, not the repo root: every entry point here runs via
    # `uv run` from inside data-platform/ (see the Makefile), so "warehouse"
    # is data-platform/warehouse in practice.
    warehouse_root: Path = Path("warehouse")

    metabase_url: str = "http://localhost:3001"
    metabase_user: str = "admin@ies.local"
    metabase_password: str = "IesAdmin123!"

    # Symmetric key for the pii_token vault's pgcrypto encryption (V11
    # migration). Same "local-dev default, override via IES_-prefixed env
    # var in a real deployment" pattern as metabase_password above -- never
    # a real production secret in this file.
    pii_encryption_key: str = "ies-local-dev-pii-vault-key"

    @property
    def bronze_root(self) -> Path:
        """Append-only Delta landings of the operational tables."""
        return self.warehouse_root / "bronze"

    @property
    def duckdb_path(self) -> Path:
        """The dbt-built warehouse file, matching profiles.yml's own
        default (`../../warehouse/ies.duckdb`, relative to dbt/ies_warehouse/
        -- the same path as warehouse_root/ies.duckdb from here)."""
        return self.warehouse_root / "ies.duckdb"
