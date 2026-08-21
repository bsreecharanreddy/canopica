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

    operational_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"
    serving_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_serving"
    warehouse_root: Path = Path("data-platform/warehouse")

    @property
    def bronze_root(self) -> Path:
        """Append-only Delta landings of the operational tables."""
        return self.warehouse_root / "bronze"
