"""Runtime configuration for the Canopica data platform."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings shared by every data-platform entry point.

    Every value has a local-development default so a fresh clone runs without a
    ``.env`` file; the Compose stack overrides them with ``CANOPICA_``-prefixed
    environment variables.
    """

    model_config = SettingsConfigDict(env_prefix="CANOPICA_", env_file=".env", extra="ignore")

    # These are fixed placeholder credentials for the local Docker Compose
    # stack only (infra/docker-compose.yml) -- never reachable outside
    # localhost/the Compose network, and overridable via CANOPICA_-prefixed env
    # vars (see infra/.env.example). Not production secrets; a real
    # deployment supplies real values through the environment, not this file.
    operational_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"
    serving_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_serving"
    # Relative to cwd, not the repo root: every entry point here runs via
    # `uv run` from inside data-platform/ (see the Makefile), so "warehouse"
    # is data-platform/warehouse in practice.
    warehouse_root: Path = Path("warehouse")

    metabase_url: str = "http://localhost:3001"
    metabase_user: str = "admin@canopica.local"
    metabase_password: str = "CanopicaAdmin123!"

    @property
    def bronze_root(self) -> Path:
        """Append-only Delta landings of the operational tables."""
        return self.warehouse_root / "bronze"

    @property
    def duckdb_path(self) -> Path:
        """The dbt-built warehouse file, matching profiles.yml's own
        default (`../../warehouse/canopica.duckdb`, relative to dbt/canopica_warehouse/
        -- the same path as warehouse_root/canopica.duckdb from here)."""
        return self.warehouse_root / "canopica.duckdb"
