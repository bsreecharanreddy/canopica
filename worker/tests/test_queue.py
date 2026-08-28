from __future__ import annotations

import time

import psycopg
import pytest

from canopica_worker.config import Settings
from canopica_worker.queue import archive, delete, read, send

# Needs a real pgmq-enabled Postgres (Testcontainers, see conftest.py).
pytestmark = pytest.mark.integration


def test_read_on_an_empty_queue_returns_none(test_queue: str, settings: Settings) -> None:
    assert read(test_queue, visibility_timeout_seconds=30, settings=settings) is None


def test_send_and_read_returns_the_message(test_queue: str, settings: Settings) -> None:
    send(test_queue, {"hello": "world"}, settings=settings)

    message = read(test_queue, visibility_timeout_seconds=30, settings=settings)

    assert message is not None
    assert message.message == {"hello": "world"}
    assert message.read_ct == 1


def test_read_locks_the_message_until_visibility_timeout_expires(
    test_queue: str, settings: Settings
) -> None:
    send(test_queue, {"hello": "world"}, settings=settings)
    first = read(test_queue, visibility_timeout_seconds=1, settings=settings)
    assert first is not None

    # Still locked -- a second reader sees an empty queue, not the same
    # message twice, which is the whole point of the visibility timeout.
    assert read(test_queue, visibility_timeout_seconds=1, settings=settings) is None

    time.sleep(1.5)

    second = read(test_queue, visibility_timeout_seconds=30, settings=settings)
    assert second is not None
    assert second.msg_id == first.msg_id
    assert second.read_ct == 2


def test_delete_removes_the_message_for_good(test_queue: str, settings: Settings) -> None:
    send(test_queue, {"hello": "world"}, settings=settings)
    message = read(test_queue, visibility_timeout_seconds=30, settings=settings)
    assert message is not None

    assert delete(test_queue, message.msg_id, settings=settings) is True
    assert read(test_queue, visibility_timeout_seconds=30, settings=settings) is None


def test_archive_moves_the_message_out_of_the_live_queue_but_keeps_it_inspectable(
    test_queue: str, settings: Settings
) -> None:
    send(test_queue, {"hello": "world"}, settings=settings)
    message = read(test_queue, visibility_timeout_seconds=30, settings=settings)
    assert message is not None

    assert archive(test_queue, message.msg_id, settings=settings) is True
    assert read(test_queue, visibility_timeout_seconds=30, settings=settings) is None

    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(f"select message from pgmq.a_{test_queue} where msg_id = %s", (message.msg_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == {"hello": "world"}
