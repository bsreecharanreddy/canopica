"""Deterministic grounding check (design doc §2.3, constraint 21): every
dollar figure the drafted summary asserts must trace back to the real
diff or either evaluation's own trace -- never an LLM judge call, exact
value comparison only. Same posture `correspondence/validate.py` already
establishes for notice content.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from canopica_ai.qc_assistant.draft import DiscrepancyContext

# Optional minus on either side of the $ (a negative diff is a real,
# expected value here, unlike correspondence's own always-positive benefit
# amounts, and Python's own f"${value}" formatting of a negative Decimal
# puts the sign after the dollar sign, e.g. "$-34.00" -- matched here
# regardless of which side the model reproduces it on), optional thousands
# separator, mandatory cents.
_MONEY_PATTERN = re.compile(r"-?\$-?[\d,]+\.\d{2}")


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _walk_numbers(value: Any) -> list[Decimal]:
    """Every numeric leaf in a nested dict/list structure -- both traces
    are loosely-typed dicts of named DMN decision values (design doc
    §3.4.1), not a fixed schema, so this walks rather than reads named
    fields. Same helper shape `correspondence/validate.py`'s own
    `_walk_numbers` already establishes."""
    found: list[Decimal] = []
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_numbers(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_numbers(item))
    else:
        decimal_value = _as_decimal(value)
        if decimal_value is not None:
            found.append(decimal_value)
    return found


def known_good_amounts(context: DiscrepancyContext) -> set[Decimal]:
    amounts = {
        context.original_amount, context.reproduced_amount, context.error_amount,
        -context.error_amount,
    }
    amounts.update(_walk_numbers(context.original_trace))
    amounts.update(_walk_numbers(context.reproduced_trace))
    return {amount.quantize(Decimal("0.01")) for amount in amounts}


def grounding_errors(summary: str, known_amounts: set[Decimal]) -> list[str]:
    errors: list[str] = []
    for token in _MONEY_PATTERN.findall(summary):
        amount = Decimal(token.replace("$", "").replace(",", "")).quantize(Decimal("0.01"))
        if amount not in known_amounts:
            errors.append(
                f"summary asserts {token}, which does not match any figure in this case's own "
                "diff or trace records"
            )
    return errors
