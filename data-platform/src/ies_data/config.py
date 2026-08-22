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

    operational_dsn: str = "postgresql://ies_app:ies_app@localhost:5432/ies_operational"
    serving_dsn: str = "postgresql://ies_app:ies_app@localhost:5432/ies_serving"
    # Relative to cwd, not the repo root: every entry point here runs via
    # `uv run` from inside data-platform/ (see the Makefile), so "warehouse"
    # is data-platform/warehouse in practice.
    warehouse_root: Path = Path("warehouse")

    metabase_url: str = "http://localhost:3001"
    metabase_user: str = "admin@ies.local"
    metabase_password: str = "IesAdmin123!"

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
