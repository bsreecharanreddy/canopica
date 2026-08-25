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

from typing import Any

from pydantic import BaseModel

from canopica_ai.analytics_copilot.jwt_auth import decode_worker_token
from canopica_ai.analytics_copilot.metric_query import run_metric_query
from canopica_ai.analytics_copilot.tools import (
    QUERY_METRIC_TOOL_NAME,
    QueryMetricArgs,
    tool_list_for_role,
)
from canopica_ai.common.llm_client import OllamaClient, ToolCallingLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings

# Priority only matters for which single role's tool list gets used when a
# token somehow carries more than one -- Phase 2's tool list is identical
# across all three (tools.py), so this never changes what gets exposed.
_ROLE_PRIORITY = ("ADMIN", "SUPERVISOR", "WORKER")


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

        call = llm_client.generate_tool_call(question, tools)
        if call.name != QUERY_METRIC_TOOL_NAME:
            raise UnsupportedToolError(f"model selected unsupported tool {call.name!r}")

        # Raises pydantic.ValidationError for a hallucinated metric name --
        # deliberately left to propagate rather than caught here, so a bad
        # tool call fails validation instead of silently falling back to
        # something else (Task 5 plan Step 5).
        args = QueryMetricArgs.model_validate(call.arguments)

        execution = run_metric_query(
            metric_names=[args.metric_name],
            group_by_names=args.group_by,
            filters=args.filters or (),
            settings=settings,
        )
        return AnalyticsAnswer(
            compiled_sql=execution.compiled_sql,
            result_rows=execution.rows,
            metric_names_used=[args.metric_name],
        )
