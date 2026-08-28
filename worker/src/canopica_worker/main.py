"""The worker's entrypoint: a generic poll/dispatch loop over pgmq queues,
plus the two queues this phase actually needs (design doc §2.2). Task 1
wired each queue to a placeholder handler that only logged and
acknowledged a message; Task 3 replaces `document_intake`'s handler with
real classification, Task 5 replaces `correspondence_dispatch`'s with real
drafting. The loop mechanics (read, dispatch, delete-on-success,
archive-after-`max_delivery_attempts`) are Task 1's real deliverable and
don't change when those handlers do.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from canopica_worker import correspondence_consumer, document_intake_consumer
from canopica_worker.config import Settings
from canopica_worker.queue import Message, archive, delete, read

logger = logging.getLogger("canopica_worker")

Handler = Callable[[Message], None]


def poll_once(queue_name: str, handler: Handler, *, settings: Settings) -> bool:
    """One read-dispatch cycle against `queue_name`. Returns whether a
    message was found (so `run_forever` only sleeps once every queue came
    back empty, not on every cycle)."""
    message = read(
        queue_name,
        visibility_timeout_seconds=settings.visibility_timeout_seconds,
        settings=settings,
    )
    if message is None:
        return False
    try:
        handler(message)
    except Exception:
        logger.exception(
            "handler failed for %s msg_id=%s (attempt %s/%s)",
            queue_name,
            message.msg_id,
            message.read_ct,
            settings.max_delivery_attempts,
        )
        if message.read_ct >= settings.max_delivery_attempts:
            archive(queue_name, message.msg_id, settings=settings)
            logger.error(
                "archived %s msg_id=%s after %s failed attempts",
                queue_name,
                message.msg_id,
                message.read_ct,
            )
        # Below the limit: leave it locked. It becomes visible again once
        # the visibility timeout expires, and the next poll retries it --
        # no explicit re-queue call needed, that's pgmq's own redelivery.
        return True
    delete(queue_name, message.msg_id, settings=settings)
    return True


def run_forever(handlers: dict[str, Handler], *, settings: Settings | None = None) -> None:
    """Polls every queue in `handlers` in turn, forever. Sleeps
    `poll_interval_seconds` only when a full pass over every queue found
    nothing -- an active queue gets drained without an artificial delay
    between messages."""
    settings = settings or Settings()
    while True:
        found_any = False
        for queue_name, handler in handlers.items():
            if poll_once(queue_name, handler, settings=settings):
                found_any = True
        if not found_any:
            time.sleep(settings.poll_interval_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    run_forever(
        {
            settings.document_intake_queue: document_intake_consumer.build_handler(
                settings=settings
            ),
            settings.correspondence_dispatch_queue: correspondence_consumer.build_handler(
                settings=settings
            ),
        },
        settings=settings,
    )


if __name__ == "__main__":
    main()
