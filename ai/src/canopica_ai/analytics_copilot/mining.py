"""SOP Process-Improvement Mining (Phase 4 Task 8, design doc §2.6):
NL -> tool-call -> execute -> summarize, extending the *existing*
Analytics Copilot mechanism rather than a new architecture. `mine_process_
improvements` calls `service.ask()` unchanged for the tool-calling half
(same authorization-gated, role-scoped tool list, resolved before the LLM
ever sees a tool exists), then makes exactly one further LLM call --
never a second tool-calling round -- to synthesize a narrative from the
rows that query actually returned.

Grounded the same way `sla_monitor.summarize` grounds a stall reason:
draft, check the draft only names numbers that actually appear in the
real result rows, retry once, raise rather than persist an ungrounded
narrative. This component has no write path at all (constraint 22) --
`mine_process_improvements` returns the narrative to its caller; nothing
here inserts or updates anything.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel

from canopica_ai.analytics_copilot.service import AnalyticsAnswer, ask
from canopica_ai.common.llm_client import (
    OllamaClient,
    StructuredLlmClient,
    ToolCallingLlmClient,
)
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings

# Same "one retry is worth it, two is evidence" reasoning every other
# grounded-draft call site in this repo already applies.
_MAX_ATTEMPTS = 2

_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


class MiningLlmClient(ToolCallingLlmClient, StructuredLlmClient, Protocol):
    """`mine_process_improvements` needs both halves of `ask()`'s own
    tool-calling client and a structured-generation client for the
    narrative step -- a small combined protocol rather than widening
    either existing one, same interface-segregation reasoning
    `llm_client.py`'s own docstrings already give for keeping
    `ToolCallingLlmClient`/`StructuredLlmClient` separate from each
    other."""


class MiningAnswer(BaseModel):
    compiled_sql: str
    result_rows: list[dict[str, Any]]
    metric_names_used: list[str]
    narrative: str


class NarrativeDraftError(RuntimeError):
    """The model could not produce a schema-valid narrative after
    `_MAX_ATTEMPTS` tries. Raised rather than falling back to a canned
    string, same posture every other draft-error class in this repo
    already establishes."""


class NarrativeGroundingError(RuntimeError):
    """The drafted narrative named a number that matches no value the
    metric query actually returned, after every retry -- raised rather
    than persisting a possibly-invented figure."""


class _DraftNarrative(BaseModel):
    narrative: str


def _prompt(question: str, answer: AnalyticsAnswer) -> str:
    metrics = ", ".join(answer.metric_names_used)
    rows_text = "\n".join(str(row) for row in answer.result_rows) or "(no rows returned)"
    return (
        "You are a process-improvement analyst for a SNAP benefits agency. A metric query "
        f"already ran against the question below and returned real rows. Write one short "
        "paragraph (2-4 sentences) suggesting a concrete process improvement grounded in "
        "these results.\n\n"
        f"Question: {question}\n"
        f"Metric(s) queried: {metrics}\n"
        f"Result rows:\n{rows_text}\n\n"
        "Rules that matter more than sounding polished:\n"
        "- Use ONLY the numbers shown in the result rows above. Never introduce a number "
        "that isn't already there.\n"
        "- This is an advisory suggestion for a human process owner to consider -- do not "
        "phrase it as a decision, an instruction to change a system, or a fact about a cause "
        "the data doesn't establish.\n"
    )


def draft_narrative(
    question: str,
    answer: AnalyticsAnswer,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    prompt = _prompt(question, answer)

    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftNarrative)
        try:
            return _DraftNarrative.model_validate_json(response.text).narrative
        except ValueError as error:
            last_error = error
            continue

    raise NarrativeDraftError(
        f"could not draft a process-improvement narrative after {_MAX_ATTEMPTS} attempts: "
        f"{last_error}"
    )


def _known_numbers(rows: list[dict[str, Any]]) -> set[str]:
    known: set[str] = set()
    for row in rows:
        for value in row.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            known.add(str(int(value)))
            known.add(str(round(value)))
            # Ratio metrics (e.g. notice_rejection_rate) are near-certain to be
            # spoken of as a percentage rather than a fraction.
            percent = value * 100
            known.add(str(int(percent)))
            known.add(str(round(percent)))
    return known


def grounding_errors(narrative: str, answer: AnalyticsAnswer) -> list[str]:
    known = _known_numbers(answer.result_rows)
    errors: list[str] = []
    for match in _NUMBER_PATTERN.findall(narrative):
        normalized = match.replace(",", "").split(".")[0].lstrip("-") or "0"
        if normalized not in known:
            errors.append(
                f"narrative states '{match}', which matches no value the metric query "
                "actually returned"
            )
    return errors


def draft_grounded_narrative(
    question: str,
    answer: AnalyticsAnswer,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    last_errors: list[str] = []
    for _ in range(_MAX_ATTEMPTS):
        narrative = draft_narrative(question, answer, settings=settings, llm_client=llm_client)
        last_errors = grounding_errors(narrative, answer)
        if not last_errors:
            return narrative

    raise NarrativeGroundingError(
        f"drafted narrative failed grounding after {_MAX_ATTEMPTS} attempts: {last_errors}"
    )


def mine_process_improvements(
    question: str,
    jwt: str,
    *,
    settings: Settings | None = None,
    llm_client: MiningLlmClient | None = None,
) -> MiningAnswer:
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)

    with traced_ai_operation("analytics_copilot.mine_process_improvements"):
        answer = ask(question, jwt, settings=settings, llm_client=llm_client)
        narrative = draft_grounded_narrative(
            question, answer, settings=settings, llm_client=llm_client
        )
        return MiningAnswer(
            compiled_sql=answer.compiled_sql,
            result_rows=answer.result_rows,
            metric_names_used=answer.metric_names_used,
            narrative=narrative,
        )
