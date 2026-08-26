"""OpenTelemetry span instrumentation for the pipeline stages (extract,
dbt build, materialize, provision_metabase). Exports to the same Jaeger the
API exports to (infra/docker-compose.yml's `jaeger` service) via
OTLP/HTTP, so a real `make pipeline` run and a real API request land
side by side in one place -- Phase 1b Task 9's "traces in Jaeger" check.

Every pipeline entry point (`canopica_data.pipeline`, and each Airflow task
function in `infra/airflow/dags/canopica_pipeline_dag.py`) imports and calls
`traced()` independently, in its own process -- `init_tracer()` is
idempotent (module-level cache) so repeated calls within one process reuse
the same `TracerProvider` rather than registering a new exporter each time.

`SimpleSpanProcessor`, not `BatchSpanProcessor`: each of these processes is
short-lived (a one-shot pipeline run, or a single Airflow task subprocess)
and emits at most a handful of spans, so there is no throughput case for
batching, and no risk of a background export thread losing buffered spans
when the process exits before a batch flush would otherwise fire.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from canopica_data.config import Settings


@lru_cache(maxsize=1)
def _registered_tracer(otel_exporter_endpoint: str) -> trace.Tracer:
    """`lru_cache` (keyed on the one value that can vary, the endpoint
    string) is what makes this idempotent per process, without a mutable
    module-level global -- the endpoint is fixed for the life of a process
    (driven by CANOPICA_OTEL_EXPORTER_ENDPOINT), so the cache never actually sees
    a second key in practice."""
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "canopica-data-platform"}))
    exporter = OTLPSpanExporter(endpoint=otel_exporter_endpoint, timeout=5)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("canopica_data")


def init_tracer(settings: Settings | None = None) -> trace.Tracer:
    """Registers the process-wide `TracerProvider` on first call; every
    later call (from the same or a different pipeline stage) returns the
    tracer already registered rather than re-initializing the exporter."""
    resolved_settings = settings or Settings()
    return _registered_tracer(resolved_settings.otel_exporter_endpoint)


@contextmanager
def traced(span_name: str) -> Iterator[None]:
    """Wraps a pipeline stage in a span. A stage run standalone (e.g. an
    Airflow task's own subprocess) becomes the root of its own trace; a
    stage run from within `canopica_data.pipeline.main()`, which opens no span of
    its own, likewise becomes its own root -- there is deliberately no
    cross-stage parent span, so each stage is independently visible in
    Jaeger regardless of which entry point ran it."""
    with init_tracer().start_as_current_span(span_name):
        yield
