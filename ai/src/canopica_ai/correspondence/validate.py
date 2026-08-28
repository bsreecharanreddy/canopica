"""The deterministic pre-check (design doc §2.4), reusing Phase 2's
eval-gate shape rather than inventing a new one -- the same "cheap,
zero-noise check before a human ever sees the draft" posture §2.6 of the
Phase 2 design doc's citation pre-check already established. Runs on the
*fully assembled* notice content, after `service.py`'s programmatic
substitution, so it catches both an unfilled template slot and a dollar
amount/date the LLM's own explanation asserted that doesn't actually
trace back to this determination -- never an LLM judge call, exact
string/value comparison only.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from canopica_ai.correspondence.schema import DeterminationRecord, ValidationResult

# Matches an unresolved template placeholder left behind by service.py's
# substitution (e.g. a slot name it forgot to supply) -- deliberately not
# raising at substitution time, so a missing slot is a reviewable
# validation failure like any other, not a crashed worker message.
_UNFILLED_SLOT_PATTERN = re.compile(r"\{[a-z_]+\}")

# What the draft.py prompt instructs the model to use for money, and what
# service.py's own programmatic substitution produces -- optional
# thousands separator, mandatory cents.
_MONEY_PATTERN = re.compile(r"\$[\d,]+\.\d{2}")

# ISO dates only -- the only date format this system's own templates and
# trace data ever produce (LocalDate.toString() in Java, date.isoformat()
# in Python).
_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


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
    """Every numeric leaf in a nested dict/list structure -- `trace_facts`
    and `trace_decisions` are both loosely-typed dicts of named DMN/intake
    values (design doc §3.4.1), not a fixed schema, so this walks rather
    than reads named fields."""
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


def _known_good_amounts(determination: DeterminationRecord) -> set[Decimal]:
    amounts = {determination.benefit_amount}
    amounts.update(_walk_numbers(determination.trace_facts))
    amounts.update(_walk_numbers(determination.trace_decisions))
    return {amount.quantize(Decimal("0.01")) for amount in amounts}


def _known_good_dates(determination: DeterminationRecord) -> set[str]:
    return {
        determination.benefit_month.isoformat(),
        determination.as_of_date.isoformat(),
        determination.decided_at.date().isoformat(),
    }


def validate(content: str, determination: DeterminationRecord) -> ValidationResult:
    errors: list[str] = []

    if _UNFILLED_SLOT_PATTERN.search(content):
        errors.append("notice content has an unfilled template slot")

    known_amounts = _known_good_amounts(determination)
    for token in _MONEY_PATTERN.findall(content):
        amount = Decimal(token.replace("$", "").replace(",", "")).quantize(Decimal("0.01"))
        if amount not in known_amounts:
            errors.append(
                f"notice content asserts {token}, which does not match any figure "
                "in this determination's own record"
            )

    known_dates = _known_good_dates(determination)
    for token in _DATE_PATTERN.findall(content):
        if token not in known_dates:
            errors.append(
                f"notice content asserts {token}, which does not match any date "
                "in this determination's own record"
            )

    return ValidationResult(passed=not errors, errors=errors)
