# canopica-worker

Phase 3's async worker: the sole consumer of the two `pgmq` queues
`document_intake` and `correspondence_dispatch`. Polls both, calling into
`ai/`'s document-classification and correspondence-drafting pipelines as a
library — this project owns orchestration (enqueue, dequeue, retry,
archive-on-exhaustion), never model inference itself.

See `docs/design/2026-08-27-phase-3-case-intake-communication-ai-design.md`
§2.2 for why this exists and why it's Python, and
`docs/plans/2026-08-27-phase-3-implementation-plan.md` Task 1 for what it
covers so far.

```
uv run python -m canopica_worker.main
```
