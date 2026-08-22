"""
uv run python -m ies_data.ingestion.cli --tables all
uv run python -m ies_data.ingestion.cli --tables person,household
"""

from __future__ import annotations

import argparse
import sys

from ies_data.config import Settings
from ies_data.ingestion.extract import ALL_TABLES, extract_to_bronze


def main() -> None:
    parser = argparse.ArgumentParser(prog="ies_data.ingestion.cli")
    parser.add_argument(
        "--tables",
        required=True,
        help="'all', or a comma-separated list of operational table names",
    )
    args = parser.parse_args()

    tables = list(ALL_TABLES) if args.tables == "all" else args.tables.split(",")

    settings = Settings()
    counts = extract_to_bronze(settings.operational_dsn, settings.bronze_root, tables)
    for table, count in counts.items():
        print(f"{table}: {count} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
