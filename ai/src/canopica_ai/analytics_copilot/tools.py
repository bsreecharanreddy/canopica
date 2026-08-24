"""Step 1 (Task 5 plan): builds the Analytics Copilot's MCP tool list *per
caller role*, resolved before any tool is even offered to the LLM -- design
doc §2.4's "authorization before query compilation" applied at the
earliest possible point, tool exposure, not after a query is built.

For Phase 2's scope, every worker-realm role gets the same one tool:
every metric in Task 4's manifest is already caseload-aggregate, never
row-level PII, so there is nothing to narrow by role today. The role
parameter and the set below exist as the enforcement point for a future
metric that *does* need narrowing -- stated explicitly so a later reader
does not mistake this for a no-op left in by accident.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from canopica_ai.analytics_copilot.metric_catalog import known_metric_names, load_known_metrics
from canopica_ai.common.llm_client import ToolSpec

QUERY_METRIC_TOOL_NAME = "query_metric"

_ROLES_WITH_ANALYTICS_ACCESS = frozenset({"WORKER", "SUPERVISOR", "ADMIN"})


class UnknownMetricError(ValueError):
    """The caller (an LLM tool call, or anything else) named a metric that
    is not in Task 4's manifest -- a hallucination caught at tool-argument
    validation, before any query is compiled or run."""


class QueryMetricArgs(BaseModel):
    """The `query_metric` tool's arguments. `metric_name` is checked
    against Task 4's real manifest on every validation, not a name list
    frozen at import time, so a metric added to `metrics.yml` is queryable
    without a code change here."""

    metric_name: str
    group_by: list[str] = Field(default_factory=list)
    filters: list[str] | None = None

    @field_validator("metric_name")
    @classmethod
    def _metric_name_is_known(cls, value: str) -> str:
        known = known_metric_names()
        if value not in known:
            raise UnknownMetricError(
                f"{value!r} is not a known metric; must be one of {sorted(known)}"
            )
        return value


def tool_list_for_role(role: str) -> list[ToolSpec]:
    """The MCP tools `role` may call, resolved before any LLM prompt is
    built -- an empty list here means the LLM is never even told the tool
    exists, not merely blocked from using it."""
    if role not in _ROLES_WITH_ANALYTICS_ACCESS:
        return []

    metrics = load_known_metrics()
    catalog = "; ".join(f"{metric.name} ({metric.description})" for metric in metrics)
    return [
        ToolSpec(
            name=QUERY_METRIC_TOOL_NAME,
            description=(
                "Query one governed metric from the Canopica semantic layer. "
                f"metric_name must be exactly one of: {catalog}. "
                "group_by names dimensions/entities as entity__dimension "
                "(e.g. determination__is_expedited)."
            ),
            parameters=QueryMetricArgs.model_json_schema(),
        )
    ]
