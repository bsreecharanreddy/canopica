"""
uv run python -m ies_data.serving.cli
"""

from __future__ import annotations

import sys

from ies_data.config import Settings
from ies_data.serving.materialize import materialize_gold


def main() -> None:
    settings = Settings()
    counts = materialize_gold(settings.duckdb_path, settings.serving_dsn)
    for mart, count in counts.items():
        print(f"{mart}: {count} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
