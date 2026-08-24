"""The wire contract between the portal and the rule-authoring copilot
(design doc §2.3).

Two things this module is responsible for, both load-bearing:

1. **Money never touches a float.** Every figure here is a `Decimal` in
   Python and a decimal *string* on the wire, the same end-to-end rule the
   portal's own DTOs and `portal/web/src/api/types.ts` already hold to.
2. **A proposed value has to be in its unit's domain before anyone sees
   it.** These are the bounds a benefit figure cannot be outside of
   regardless of what any policy document says -- a negative allotment, a
   deduction rate above 100%. They are not a judgement about whether a
   change is *right*; that judgement is the human reviewer's, and the whole
   design puts it there deliberately.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, model_validator
from pydantic.alias_generators import to_camel

# A `Decimal` whose JSON schema is a plain string. Both halves matter:
# Decimal keeps money exact, and overriding the schema keeps it a simple
# `{"type": "string"}` -- Pydantic's own Decimal schema is an anyOf around a
# negative-lookahead regex, which is exactly the shape a constrained
# decoder's grammar compiler is least likely to accept. Serialising as a
# string is also what the rest of this system already does with money.
DecimalValue = Annotated[
    Decimal,
    WithJsonSchema({"type": "string", "description": 'a plain decimal number, e.g. "298"'}),
]

# Mirrors V3's `unit` CHECK constraint and its `household_size between 1 and
# 8` CHECK -- caught here rather than as a constraint violation several
# layers later, where the message names a Postgres constraint instead of a
# policy figure.
Unit = Literal["USD_PER_MONTH", "RATE", "COUNT"]
HouseholdSize = Annotated[int, Field(ge=1, le=8)]


class WireModel(BaseModel):
    """camelCase on the wire, snake_case in Python -- the same convention
    `qa/api.py` states for its own request models, applied once here
    instead of per field, since these models have enough fields for
    per-field aliases to be a place to make mistakes."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True
    )


def _check_within_unit_domain(value: Decimal, unit: Unit) -> None:
    if value < 0:
        raise ValueError(f"{unit} value cannot be negative (got {value})")
    if unit == "RATE" and value > 1:
        raise ValueError(f"a RATE is a fraction of 1, not a percentage (got {value})")
    if unit == "COUNT" and value != value.to_integral_value():
        raise ValueError(f"a COUNT must be a whole number (got {value})")


class CurrentParameter(WireModel):
    """One figure from the parameter set being diffed against, supplied by
    the portal. This service has no database access of its own -- everything
    it knows about what is currently in force arrives in the request."""

    name: str
    household_size: HouseholdSize | None = None
    value: DecimalValue
    unit: Unit


class ProposedParameter(WireModel):
    """One line of the diff a human reviewer will accept or reject.

    `old_value` and `unit` are copied from the current parameter set by the
    service, never taken from the model: they are what the change is
    measured *against*, and a wrong one would make the reviewer's screen
    misdescribe what is actually changing.
    """

    name: str
    household_size: HouseholdSize | None = None
    old_value: DecimalValue
    new_value: DecimalValue
    unit: Unit
    rationale: str

    @model_validator(mode="after")
    def _new_value_is_within_its_units_domain(self) -> ProposedParameter:
        _check_within_unit_domain(self.new_value, self.unit)
        return self


class ParameterProposal(WireModel):
    """A complete, reviewable draft. Carries its own provenance for the same
    reason `ai.policy_qa_answer` does (design doc §2.2): "which model, under
    which prompt, from which excerpt" has to be answerable about a figure
    that may end up deciding a benefit amount."""

    parameter_set_id: UUID
    proposed_values: list[ProposedParameter]
    source_excerpt: str
    generation_model: str
    prompt_version: str
