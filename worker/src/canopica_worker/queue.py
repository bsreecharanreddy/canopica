"""Thin wrapper over pgmq's own SQL functions (`pgmq.send`/`read`/`delete`/
`archive`) -- the sole interface `document_intake_consumer.py` (Task 3) and
`correspondence_consumer.py` (Task 5) use; neither talks to pgmq's SQL
functions directly (design doc §2.2).

Same `with psycopg.connect(dsn) as conn, conn.cursor() as cur:` pattern
`ai/`'s own `qa/provenance.py` already uses -- the connection context
manager commits on a clean exit and rolls back on an exception, so every
function below is one transaction, no explicit `commit()` needed.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import psycopg
from pydantic import BaseModel

from canopica_worker.config import Settings


class Message(BaseModel):
    """One row read back from `pgmq.read()`."""

    msg_id: int
    read_ct: int
    enqueued_at: datetime
    vt: datetime
    message: dict[str, Any]


def send(queue_name: str, message: dict[str, Any], *, settings: Settings | None = None) -> int:
    """Enqueues `message` onto `queue_name`, returning its `msg_id`.

    Callers outside this project (the API's own `@Transactional` methods)
    call `pgmq.send` directly in JDBC, inside their own transaction --
    constraint 17 of the Phase 3 plan. This function is for the worker's
    own use (tests, and any future worker-initiated enqueue), not that
    cross-language boundary.
    """
    settings = settings or Settings()
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select * from pgmq.send(%s, %s::jsonb)",
            (queue_name, json.dumps(message)),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def read(
    queue_name: str, *, visibility_timeout_seconds: int, settings: Settings | None = None
) -> Message | None:
    """Reads and locks (for `visibility_timeout_seconds`) the oldest visible
    message on `queue_name`, or `None` if the queue is empty. A message
    read but never `delete`d or `archive`d becomes visible again once the
    lock expires -- pgmq's own at-least-once redelivery, which is what
    makes a crashed consumer safe to just retry rather than a data-loss
    event."""
    settings = settings or Settings()
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select msg_id, read_ct, enqueued_at, vt, message from pgmq.read(%s, %s, 1)",
            (queue_name, visibility_timeout_seconds),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return Message(msg_id=row[0], read_ct=row[1], enqueued_at=row[2], vt=row[3], message=row[4])


def delete(queue_name: str, msg_id: int, *, settings: Settings | None = None) -> bool:
    """Removes a message for good -- the normal path, called once its
    processing has actually committed."""
    settings = settings or Settings()
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select pgmq.delete(%s, %s)", (queue_name, msg_id))
        row = cur.fetchone()
        assert row is not None
        return bool(row[0])


def archive(queue_name: str, msg_id: int, *, settings: Settings | None = None) -> bool:
    """Moves a message to pgmq's own archive table instead of retrying it
    forever -- called once `Message.read_ct` has reached
    `Settings.max_delivery_attempts`. Archived, not deleted outright: the
    message body stays inspectable for diagnosing why it kept failing,
    the same "don't silently drop" posture this project takes with a
    rejected AI draft elsewhere."""
    settings = settings or Settings()
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select pgmq.archive(%s, %s)", (queue_name, msg_id))
        row = cur.fetchone()
        assert row is not None
        return bool(row[0])
