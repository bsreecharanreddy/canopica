"""Runtime configuration for the Canopica async worker."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings, same pattern as ``canopica_ai.config.Settings``
    and ``canopica_data.config.Settings`` -- every value has a local-development
    default so a fresh clone runs without a ``.env`` file.
    """

    model_config = SettingsConfigDict(env_prefix="CANOPICA_", env_file=".env", extra="ignore")

    # Same shared operational Postgres every other service in this repo
    # writes to -- pgmq's queue tables live here too (design doc §2.2), not
    # in a separate database, which is what makes the same-transaction
    # enqueue guarantee possible in the first place.
    operational_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"

    document_intake_queue: str = "document_intake"
    correspondence_dispatch_queue: str = "correspondence_dispatch"

    # How long a message stays invisible to other readers after `read()`
    # before it's eligible to be read again -- long enough for a real
    # classify/draft LLM call plus DB writes to finish under ordinary load,
    # short enough that a genuinely crashed consumer doesn't leave a message
    # stuck for an unreasonable time. Revisit with a measured figure once
    # Task 3/5's real consumers exist; 60s is a starting default, not yet
    # load-tested.
    visibility_timeout_seconds: int = 60

    # A message that has failed this many times moves to pgmq's own archive
    # instead of being retried forever -- bounded, same "no retry-forever
    # loop" posture judge_model.py's own OpenRouter retry logic already
    # takes for a different kind of transient failure.
    max_delivery_attempts: int = 5

    # How long the poll loop sleeps between empty reads on both queues --
    # cheap enough not to matter at this scale, avoids a busy-loop against
    # an idle Postgres connection.
    poll_interval_seconds: float = 2.0

    otel_exporter_endpoint: str = "http://localhost:4318/v1/traces"
    otel_enabled: bool = True
