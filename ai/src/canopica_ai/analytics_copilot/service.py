"""Step 3 (Task 5 plan): `ask()` orchestrates the Analytics Copilot end to
end -- validate the caller's own worker-realm JWT, resolve their
role-scoped tool list (Step 1) *before* the LLM ever sees a tool exists,
let the LLM pick a tool and arguments (never SQL), validate those
arguments against Task 4's real metric manifest, and execute through
`metric_query.py`'s MetricFlow-compiled, locked-down-DuckDB-executed path.

`compiled_sql` on the answer is always MetricFlow's own output, satisfying
design doc §2.4's "generated SQL always shown" without separate tooling --
there is no LLM-authored SQL anywhere in this path to show instead.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from canopica_ai.analytics_copilot.jwt_auth import decode_worker_token
from canopica_ai.analytics_copilot.metric_query import MetricCompilationError, run_metric_query
from canopica_ai.analytics_copilot.tools import (
    QUERY_METRIC_TOOL_NAME,
    QueryMetricArgs,
    tool_list_for_role,
)
from canopica_ai.common.llm_client import OllamaClient, ToolCall, ToolCallingLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings

# Priority only matters for which single role's tool list gets used when a
# token somehow carries more than one -- Phase 2's tool list is identical
# across all three (tools.py), so this never changes what gets exposed.
_ROLE_PRIORITY = ("ADMIN", "SUPERVISOR", "WORKER")

# One retry, not a general resilience loop. Real failure modes observed
# live (2026-08-25, CI and an 8-sample local probe against one real
# question) against llama3.2:3b: a metric/group-by pair the semantic layer
# can't join (MetricCompilationError -- e.g. the count metric
# `determinations` grouped by a dimension only `avg_processing_days`'s
# semantic model has); a hallucinated or garbled metric_name
# (pydantic.ValidationError -- e.g. `determinations(is_expedited).
# avg_processing_days`); and a filter that bare-repeats a group_by
# dimension with no comparison (also a ValidationError, see
# `tools.RedundantGroupByFilterError`). All three come with a message that
# already names the valid options for what was asked -- strictly more
# than the model had on its first guess -- so one corrective attempt is a
# real second chance, not just asking the same question again. A model
# that gets it wrong twice still fails the caller: this is not a
# retry-until-green loop, and it is not "silently fall back to something
# else" either (Task 5 plan Step 5) -- the model must explicitly
# re-select, this service never substitutes on its own.
_MAX_QUERY_ATTEMPTS = 2

_RetryableQueryError = (ValidationError, MetricCompilationError)


def _corrective_retry_prompt(
    question: str, call: ToolCall, error: ValidationError | MetricCompilationError
) -> str:
    # json.dumps, never `!r`/str(dict): observed live (2026-08-25, a
    # 10-sample real-model batch) -- showing the model its own previous
    # call as Python's single-quoted repr primed every single one of 5
    # retries to answer with group_by as that same single-quoted string
    # instead of a JSON array, which then failed validation a second time
    # for an entirely different reason than the one being corrected. Real
    # JSON in the prompt leaves nothing wrong-shaped to imitate.
    previous_call_json = json.dumps(call.arguments)
    return (
        f"{question}\n\n"
        f"Your previous tool call was {QUERY_METRIC_TOOL_NAME}({previous_call_json}), but the "
        f"semantic layer rejected it:\n{error}\n\n"
        f"Call {QUERY_METRIC_TOOL_NAME} again with corrected arguments that resolve this."
    )


class AnalyticsAnswer(BaseModel):
    compiled_sql: str
    result_rows: list[dict[str, Any]]
    metric_names_used: list[str]


class NoAccessibleMetricsError(RuntimeError):
    """The caller holds no role with any analytics tool -- resolved before
    any LLM call, not discovered by the model failing to find a tool."""


class UnsupportedToolError(RuntimeError):
    """The model selected a tool name this service never offered it.
    Should be unreachable given the role-scoped tool list passed to
    `generate_tool_call`, but treated as a hard failure rather than
    silently ignored if a future tool list and this dispatch ever drift."""


def _resolve_role(roles: frozenset[str]) -> str | None:
    return next((role for role in _ROLE_PRIORITY if role in roles), None)


def ask(
    question: str,
    jwt: str,
    *,
    settings: Settings | None = None,
    llm_client: ToolCallingLlmClient | None = None,
) -> AnalyticsAnswer:
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)

    with traced_ai_operation("analytics_copilot.ask"):
        claims = decode_worker_token(jwt, settings=settings)
        role = _resolve_role(claims.roles)
        if role is None:
            raise NoAccessibleMetricsError(f"{claims.subject} holds no role with analytics access")

        tools = tool_list_for_role(role)
        if not tools:
            raise NoAccessibleMetricsError(f"role {role} has no analytics tools")

        prompt = question
        for attempt in range(1, _MAX_QUERY_ATTEMPTS + 1):
            call = llm_client.generate_tool_call(prompt, tools)
            if call.name != QUERY_METRIC_TOOL_NAME:
                raise UnsupportedToolError(f"model selected unsupported tool {call.name!r}")

            try:
                args = QueryMetricArgs.model_validate(call.arguments)
                execution = run_metric_query(
                    metric_names=[args.metric_name],
                    group_by_names=args.group_by,
                    filters=args.filters or (),
                    settings=settings,
                )
            except _RetryableQueryError as error:
                if attempt == _MAX_QUERY_ATTEMPTS:
                    raise
                prompt = _corrective_retry_prompt(question, call, error)
                continue

            return AnalyticsAnswer(
                compiled_sql=execution.compiled_sql,
                result_rows=execution.rows,
                metric_names_used=[args.metric_name],
            )

        raise AssertionError("unreachable: loop above always returns or raises")
