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

import ast
import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from canopica_ai.analytics_copilot.metric_catalog import known_metric_names, load_known_metrics
from canopica_ai.common.llm_client import ToolSpec

QUERY_METRIC_TOOL_NAME = "query_metric"

_ROLES_WITH_ANALYTICS_ACCESS = frozenset({"WORKER", "SUPERVISOR", "ADMIN"})


class UnknownMetricError(ValueError):
    """The caller (an LLM tool call, or anything else) named a metric that
    is not in Task 4's manifest -- a hallucination caught at tool-argument
    validation, before any query is compiled or run."""


class RedundantGroupByFilterError(ValueError):
    """A filter that targets the same entity__dimension as an entry
    already in group_by -- whether a bare name or a real comparison.
    Observed live (2026-08-25, two sampling batches of llama3.2:3b against
    one real question): 3 of 8 calls filtered on the bare dimension name
    with no comparison (e.g. filters=["determination__is_expedited"]); a
    second batch then hit the same mistake in its *dominant* shape, 6 of
    6 calls, as a real comparison instead (filters=
    ["determination__is_expedited = true"]). Both compile -- MetricFlow
    accepts either as a `WHERE` clause -- and both silently drop every
    False row instead of failing loudly, which is worse than a crash: an
    equality filter on the exact dimension you're grouping by can only
    ever leave one group standing, which defeats "broken out by X"
    regardless of whether the filter has an operator on it. The rule
    therefore keys on which *dimension* a filter targets, not on its
    syntax -- a filter narrowing a *different* dimension than the one
    being grouped by (e.g. filtering `program_code` while grouping by
    `outcome`) is completely ordinary and stays allowed."""


def _coerce_json_encoded_list(value: Any) -> Any:
    """Ollama's small local models occasionally emit an array-typed tool
    argument as a *string* rather than a native JSON array, even though
    the tool schema declares it as an array -- observed live in CI
    (2026-08-24), on both group_by and filters in the same real tool call,
    against a real question, as a JSON-encoded string (e.g.
    '["a", "b"]'); and again live (2026-08-25, a 10-sample real-model
    batch, on every one of 5 corrective retries) as a Python repr()-style,
    single-quoted string instead ("['a', 'b']") -- not valid JSON, so
    `json.loads` alone rejects it. Narrowly tolerated either way: a string
    is only accepted if it actually decodes -- as JSON first, then as a
    Python literal -- to a list; anything else (a non-list-shaped string,
    a JSON/Python object or scalar) falls through unchanged and still
    fails validation as before -- this isn't a general "accept anything"
    escape hatch.
    """
    if isinstance(value, str):
        try:
            parsed: Any = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return value
        if isinstance(parsed, list):
            return parsed
    return value


# Matches the entity__dimension identifier a filter expression *opens*
# with, whether the filter is a bare dimension name or a real comparison
# ("determination__is_expedited = true") -- both real, observed (2026-08-25)
# tool-call shapes. A filter that opens with a Jinja `{{ Dimension(...) }}`
# reference (MetricFlow's own documented syntax) doesn't match this and so
# isn't checked -- no live call has ever produced that shape here.
_LEADING_DIMENSION = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


class QueryMetricArgs(BaseModel):
    """The `query_metric` tool's arguments. `metric_name` is checked
    against Task 4's real manifest on every validation, not a name list
    frozen at import time, so a metric added to `metrics.yml` is queryable
    without a code change here."""

    metric_name: str
    group_by: list[str] = Field(default_factory=list)
    filters: list[str] | None = None

    @field_validator("group_by", "filters", mode="before")
    @classmethod
    def _coerce_json_encoded_list_fields(cls, value: Any) -> Any:
        return _coerce_json_encoded_list(value)

    @field_validator("metric_name")
    @classmethod
    def _metric_name_is_known(cls, value: str) -> str:
        known = known_metric_names()
        if value not in known:
            raise UnknownMetricError(
                f"{value!r} is not a known metric; must be one of {sorted(known)}"
            )
        return value

    @model_validator(mode="after")
    def _filters_do_not_target_a_grouped_dimension(self) -> QueryMetricArgs:
        group_by = set(self.group_by)
        overlap = sorted(
            {
                match.group(1)
                for expr in (self.filters or ())
                if (match := _LEADING_DIMENSION.match(expr.strip()))
                and match.group(1) in group_by
            }
        )
        if overlap:
            raise RedundantGroupByFilterError(
                f"{overlap} is already in group_by, so a filter on it (bare or "
                "with a comparison) can only ever leave one group standing -- "
                "that defeats \"broken out by\" that dimension. Either drop "
                "the filter, or filter a *different* dimension than the one "
                "being grouped by."
            )
        return self


def tool_list_for_role(role: str) -> list[ToolSpec]:
    """The MCP tools `role` may call, resolved before any LLM prompt is
    built -- an empty list here means the LLM is never even told the tool
    exists, not merely blocked from using it."""
    if role not in _ROLES_WITH_ANALYTICS_ACCESS:
        return []

    metrics = load_known_metrics()
    # Bare names and descriptions are kept in two separate sentences,
    # deliberately -- observed live (2026-08-25): with a single "name
    # (description)" catalog string, llama3.2:3b sometimes echoed the
    # whole "name (description)" fragment back as metric_name instead of
    # extracting just the name.
    names = ", ".join(metric.name for metric in metrics)
    descriptions = "; ".join(f"{metric.name} = {metric.description}" for metric in metrics)
    return [
        ToolSpec(
            name=QUERY_METRIC_TOOL_NAME,
            description=(
                "Query one governed metric from the Canopica semantic layer. "
                f"metric_name must be exactly one of these names, verbatim, "
                f"with nothing else added: {names}. ({descriptions}.) "
                "group_by breaks the metric out by every value of one or "
                "more dimensions, each named as entity__dimension (e.g. "
                "determination__is_expedited) -- join the metric's own "
                "entity to one of its real dimension names with a double "
                "underscore; the entity and dimension come from what the "
                "question is actually asking about, never copied as-is "
                "from this example. filters is OPTIONAL and should "
                "usually be omitted entirely -- only set it when the "
                "question explicitly asks to narrow results to a specific "
                "subset of values, and never for a dimension already in "
                "group_by (bare or with a comparison), since grouping by "
                "it already covers every one of its values."
            ),
            parameters=QueryMetricArgs.model_json_schema(),
        )
    ]
