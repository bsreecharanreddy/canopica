# SOP corpus

These three documents (`new_application.md`, `reported_change.md`,
`renewal.md`) are **authored, not sourced** -- realistic but explicitly
fictional caseworker procedure documents, written for this project the
same way the synthetic applicant data (`data-platform/src/canopica_data/synthetic/`)
already is: plausible in shape and grounded in this system's own real
workflow (case statuses, verification types, expedited screening, the
7/30-day processing standard), but not a copy of any real agency's actual
SOP manual. Phase 4 design doc §2.5 states this framing explicitly.

Each `##`-level heading in these files becomes one retrieval chunk
(`corpus/index.py`) -- write new sections with that in mind: a heading
that stands alone as a citable unit, and body text that doesn't depend on
surrounding sections to make sense out of context.
