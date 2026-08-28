from __future__ import annotations

import time

import pytest

from canopica_worker.config import Settings
from canopica_worker.main import poll_once
from canopica_worker.queue import Message, read, send

pytestmark = pytest.mark.integration


def test_poll_once_returns_false_on_empty_queue(test_queue: str, settings: Settings) -> None:
    calls: list[Message] = []
    assert poll_once(test_queue, calls.append, settings=settings) is False
    assert calls == []


def test_poll_once_calls_handler_and_deletes_on_success(
    test_queue: str, settings: Settings
) -> None:
    send(test_queue, {"hello": "world"}, settings=settings)
    calls: list[Message] = []

    found = poll_once(test_queue, calls.append, settings=settings)

    assert found is True
    assert [c.message for c in calls] == [{"hello": "world"}]
    assert read(test_queue, visibility_timeout_seconds=30, settings=settings) is None


def test_poll_once_leaves_message_for_retry_when_handler_raises_and_under_attempt_limit(
    test_queue: str, settings: Settings
) -> None:
    retry_settings = settings.model_copy(
        update={"visibility_timeout_seconds": 1, "max_delivery_attempts": 5}
    )
    send(test_queue, {"hello": "world"}, settings=retry_settings)

    def always_fails(_: Message) -> None:
        raise RuntimeError("simulated processing failure")

    assert poll_once(test_queue, always_fails, settings=retry_settings) is True
    # Still locked immediately after the failed attempt.
    assert poll_once(test_queue, always_fails, settings=retry_settings) is False

    time.sleep(1.5)

    # Visible again -- redelivered, not lost.
    message = read(test_queue, visibility_timeout_seconds=30, settings=retry_settings)
    assert message is not None
    assert message.read_ct == 2


def test_poll_once_archives_message_after_max_delivery_attempts(
    test_queue: str, settings: Settings
) -> None:
    retry_settings = settings.model_copy(
        update={"visibility_timeout_seconds": 1, "max_delivery_attempts": 2}
    )
    send(test_queue, {"hello": "world"}, settings=retry_settings)

    def always_fails(_: Message) -> None:
        raise RuntimeError("simulated processing failure")

    poll_once(test_queue, always_fails, settings=retry_settings)  # attempt 1
    time.sleep(1.5)
    poll_once(test_queue, always_fails, settings=retry_settings)  # attempt 2 -- hits the limit
    time.sleep(1.5)

    # Archived, not left to retry forever.
    assert read(test_queue, visibility_timeout_seconds=30, settings=retry_settings) is None
