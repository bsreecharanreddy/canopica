from pathlib import Path

import pytest

from canopica_data.config import Settings


def test_bronze_root_derives_from_warehouse_root() -> None:
    settings = Settings(warehouse_root=Path("/tmp/wh"))
    assert settings.bronze_root == Path("/tmp/wh/bronze")


def test_settings_read_the_ies_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANOPICA_SERVING_DSN", "postgresql://elsewhere/serving")
    assert Settings().serving_dsn == "postgresql://elsewhere/serving"
