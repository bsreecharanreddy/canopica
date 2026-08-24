"""Step 2 (Task 5 plan): exposes Task 4's semantic layer to any MCP client
as one callable tool, `query_metric` -- the standard 2026 shape for
"LLM/agent talks to a governed semantic layer" (design doc §2.4), not a
bespoke protocol.

Independently runnable (`python -m canopica_ai.analytics_copilot.mcp_server`),
the same "runnable standalone, mountable into a combined app later"
pattern `policy_intelligence/rule_authoring/api.py` already establishes
for its own HTTP surface. `service.ask()` (Step 3) is the authorization
boundary for the Ollama-backed copilot -- it resolves the caller's
role-scoped tool list *before* the LLM ever sees a tool exists; this
module is the protocol-facing surface that tool call ultimately reaches,
and the one any other MCP client (Claude Desktop, etc.) would call too.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from canopica_ai.analytics_copilot.metric_query import run_metric_query
from canopica_ai.analytics_copilot.tools import QueryMetricArgs
from canopica_ai.config import Settings

server: MCPServer[None] = MCPServer("canopica-analytics-copilot")


@server.tool(
    name="query_metric",
    description="Query one governed metric from the Canopica semantic layer.",
)
def query_metric(
    metric_name: str,
    group_by: list[str] | None = None,
    filters: list[str] | None = None,
) -> dict[str, Any]:
    """Validates `metric_name` against Task 4's real manifest (raises
    `UnknownMetricError`, a `ValueError`, for a hallucinated one -- before
    `mf query` ever runs) and returns MetricFlow's compiled SQL alongside
    the rows it produced against the locked-down execution connection."""
    args = QueryMetricArgs(metric_name=metric_name, group_by=group_by or [], filters=filters)
    execution = run_metric_query(
        metric_names=[args.metric_name],
        group_by_names=args.group_by,
        filters=args.filters or (),
        settings=Settings(),
    )
    return {"compiled_sql": execution.compiled_sql, "rows": execution.rows}


if __name__ == "__main__":
    server.run(transport="stdio")
