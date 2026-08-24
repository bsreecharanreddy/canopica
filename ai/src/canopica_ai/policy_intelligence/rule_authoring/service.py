"""Rule-authoring copilot (design doc §2.3): reads a supplied policy-document
excerpt and drafts new *values* for parameters that already exist, never new
rules and never DMN table structure.

This is the capability where CLAUDE.md's governing principle has the most to
lose -- the output is a dollar amount that, once a human publishes it, the
DMN engine will use to decide real benefits. So the model's job here is
narrowed as far as it can be and still be useful:

* It chooses only `new_value` and a rationale. `old_value`, `unit`, the
  parameter's own name and household size are all taken from the current
  parameter set, which came from the database.
* Its output is schema-constrained at the sampler (Ollama's `format`), not
  parsed hopefully out of prose.
* Anything it names that isn't already in the supplied parameter set is
  refused outright rather than shown to a reviewer, where a hallucinated
  parameter would look exactly like a real one.
* Nothing here writes to `policy_parameter_set`. Publishing is the portal's
  `PolicyParameterPublishService`, and only after an explicit human accept.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.rule_authoring.schema import (
    CurrentParameter,
    DecimalValue,
    ParameterProposal,
    ProposedParameter,
)

PROMPT_VERSION = "v1"

# One attempt plus one retry. Same shape and the same reasoning as Task 2's
# grounding retry: a single bad sample from a small model is usually
# variance and worth one more roll, while a second consecutive failure is
# evidence about the request itself and should surface as an error rather
# than be papered over.
_MAX_ATTEMPTS = 2


class ProposalGenerationError(RuntimeError):
    """The model could not produce a proposal that survives validation.

    Deliberately an error rather than a partial result: half a parameter
    diff is worse than none, because the reviewer has no way to see which
    figures are missing from the screen in front of them.
    """


class _DraftParameter(BaseModel):
    """The model-facing schema -- deliberately narrower than
    `ProposedParameter`. Every field the model is *not* allowed to decide is
    absent here, so there is no path by which it could decide one.

    `household_size` is an unbounded `int | None` rather than the 1-8 bound
    the real schema carries, so an out-of-range size is caught by the
    "not in the current parameter set" check below and reported as the
    policy mistake it is, rather than as a schema violation.

    It is also deliberately *required* -- no Python default -- even though
    null is a legal value for it. Measured (2026-08-23) against the real
    model: with a default, llama3.2:3b simply omitted the key and every
    size-scoped figure silently arrived scoped to "all household sizes",
    which is a different policy statement entirely. Required means the
    constrained decoder has to emit the key, so the model has to actually
    decide rather than fall through to whatever the default happened to be.
    """

    name: str
    household_size: int | None
    new_value: DecimalValue
    rationale: str


class _DraftProposal(BaseModel):
    proposed_values: list[_DraftParameter]


_ParameterKey = tuple[str, int | None]


def _scope_label(household_size: int | None) -> str:
    """How a parameter's scope reads to a human -- used in the error message
    when the model names a parameter that doesn't exist."""
    if household_size is None:
        return "all household sizes"
    return f"household size {household_size}"


def _describe(parameter: CurrentParameter) -> str:
    """One line of the prompt's parameter list, written in the shape of the
    JSON the model has to return rather than in prose. Measured: prose
    ("household size 1") left the model to infer the mapping onto the
    `household_size` field, and it inferred wrong -- naming the field
    literally makes copying it the path of least resistance."""
    size = "null" if parameter.household_size is None else parameter.household_size
    return (
        f'- name="{parameter.name}", household_size={size} '
        f"-- currently {parameter.value} {parameter.unit}"
    )


def _proposal_prompt(document_excerpt: str, current_values: list[CurrentParameter]) -> str:
    return (
        "You are helping a benefits policy analyst update SNAP (food "
        "assistance) parameter values from a published policy document. "
        "Propose a new value only where the excerpt states one explicitly.\n"
        "Rules:\n"
        "- Only use name/household_size pairs exactly as they appear in the "
        "list below, copied character for character. Never invent a name, "
        "and never change a household_size.\n"
        "- Leave out any parameter the excerpt does not give a new value "
        "for, including one it explicitly says is unchanged.\n"
        "- A figure the excerpt states for a *range* of household sizes "
        '("sizes one through three") applies to every parameter in the list '
        "whose household_size falls in that range. Emit a separate entry "
        "for each one.\n"
        '- new_value is a plain number written as a string: "298" or "0.2". '
        "No currency symbol, no thousands separator, no words, and a rate "
        "as a fraction of 1 rather than a percentage.\n"
        "- rationale is one short sentence naming the part of the excerpt "
        "that establishes the change.\n\n"
        "Current parameter values:\n"
        + "\n".join(_describe(p) for p in current_values)
        + f"\n\nPolicy document excerpt:\n{document_excerpt}\n"
    )


def _reconcile(
    draft: _DraftProposal, current_by_key: dict[_ParameterKey, CurrentParameter]
) -> list[ProposedParameter]:
    """Turns what the model said into what the reviewer sees, taking every
    fact except `new_value` and `rationale` from the database's own copy."""
    changes: list[ProposedParameter] = []
    seen: set[_ParameterKey] = set()
    for item in draft.proposed_values:
        key: _ParameterKey = (item.name, item.household_size)
        current = current_by_key.get(key)
        if current is None:
            raise ValueError(
                f"{item.name} ({_scope_label(item.household_size)}) "
                "is not in the current parameter set"
            )
        if key in seen:
            raise ValueError(f"{item.name} was proposed more than once")
        seen.add(key)
        if item.new_value == current.value:
            # Not a change, so not a row on the diff. Restating an unchanged
            # figure is a reasonable thing for a model to do when the
            # excerpt mentions it; padding the review screen with no-op rows
            # is how a reviewer stops reading the rows carefully.
            continue
        changes.append(
            ProposedParameter(
                name=current.name,
                household_size=current.household_size,
                old_value=current.value,
                new_value=item.new_value,
                unit=current.unit,
                rationale=item.rationale,
            )
        )
    return changes


def propose_parameter_changes(
    document_excerpt: str,
    current_parameter_set_id: UUID,
    current_values: list[CurrentParameter],
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> ParameterProposal:
    """Drafts new values for `current_values` from `document_excerpt`.

    `current_values` is supplied by the caller rather than read here: this
    service has no Postgres access to the operational schema (the same
    boundary Task 2 holds, where the only database it touches is its own
    `ai` schema), so the portal fetches the effective parameter set and
    passes it in.

    Raises `ProposalGenerationError` if two consecutive attempts fail
    validation.
    """
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    current_by_key: dict[_ParameterKey, CurrentParameter] = {
        (parameter.name, parameter.household_size): parameter for parameter in current_values
    }
    prompt = _proposal_prompt(document_excerpt, current_values)

    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftProposal)
        try:
            draft = _DraftProposal.model_validate_json(response.text)
            changes = _reconcile(draft, current_by_key)
        except ValueError as error:
            # One clause, two kinds of failure, because Pydantic's
            # ValidationError *is* a ValueError: malformed JSON or a value
            # outside its unit's domain raise the former, `_reconcile`'s
            # policy-level refusals raise the latter. Both mean the same
            # thing here -- this attempt produced nothing usable.
            last_error = error
            continue
        return ParameterProposal(
            parameter_set_id=current_parameter_set_id,
            proposed_values=changes,
            source_excerpt=document_excerpt,
            generation_model=settings.ollama_generation_model,
            prompt_version=PROMPT_VERSION,
        )

    raise ProposalGenerationError(
        f"could not produce a valid proposal after {_MAX_ATTEMPTS} attempts: {last_error}"
    )

