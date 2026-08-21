"""
uv run python -m ies_data.synthetic.cli generate --count 500 --seed 42 --out households.jsonl
uv run python -m ies_data.synthetic.cli load --input households.jsonl --api http://localhost:8080
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ies_data.synthetic.generator import generate_households
from ies_data.synthetic.loader import post_households
from ies_data.synthetic.models import SyntheticHousehold


def _generate(args: argparse.Namespace) -> None:
    households = generate_households(args.count, seed=args.seed)
    with Path(args.out).open("w") as f:
        for household in households:
            f.write(household.model_dump_json() + "\n")
    print(f"Wrote {len(households)} households to {args.out}", file=sys.stderr)


def _load(args: argparse.Namespace) -> None:
    households = [
        SyntheticHousehold.model_validate_json(line)
        for line in Path(args.input).read_text().splitlines()
        if line.strip()
    ]
    results = post_households(households, args.api)
    print(f"Loaded {len(results)} households into {args.api}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ies_data.synthetic.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate households to a JSONL file")
    generate_parser.add_argument("--count", type=int, required=True)
    generate_parser.add_argument("--seed", type=int, required=True)
    generate_parser.add_argument("--out", required=True)
    generate_parser.set_defaults(func=_generate)

    load_parser = subparsers.add_parser("load", help="POST a JSONL file of households to the API")
    load_parser.add_argument("--input", required=True)
    load_parser.add_argument("--api", required=True, help="Base URL, e.g. http://localhost:8080")
    load_parser.set_defaults(func=_load)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
