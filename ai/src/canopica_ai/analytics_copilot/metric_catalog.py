"""Reads Task 4's own metric manifest (`data-platform/dbt/canopica_warehouse/
models/semantic/metrics.yml`) as the single source of truth for which
metric names the Analytics Copilot may ever expose or query -- the same
static-YAML-read approach `data-platform/tests/test_metric_semantics.py`
already uses to check the manifest against the gold marts, applied here to
check the copilot's tool surface against the manifest instead.

A plain YAML read, not MetricFlow's own manifest parser: this module only
needs names and descriptions to build an MCP tool schema, not a compiled
semantic model. `metric_query.py` is what actually asks MetricFlow to
resolve a query against the real manifest, where an unrecognized dimension
or group-by fails for real rather than by a name-list lookup here.
"""

from __future__ import annotations

import yaml
from pydantic import BaseModel

from canopica_ai.config import Settings


class MetricDefinition(BaseModel):
    name: str
    description: str


def load_known_metrics(*, settings: Settings | None = None) -> list[MetricDefinition]:
    settings = settings or Settings()
    path = settings.data_platform_dbt_project_dir / "models" / "semantic" / "metrics.yml"
    manifest = yaml.safe_load(path.read_text())
    return [
        MetricDefinition(name=metric["name"], description=metric["description"].strip())
        for metric in manifest["metrics"]
    ]


def known_metric_names(*, settings: Settings | None = None) -> frozenset[str]:
    return frozenset(metric.name for metric in load_known_metrics(settings=settings))
