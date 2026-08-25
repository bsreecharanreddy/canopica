---
name: canopica-recurring-ci-failure
description: Use when a Canopica CI job fails with a symptom that has been seen before, or fails again after a fix that was supposed to address it — the procedure for attributing an infrastructure failure before proposing another fix for it.
---

# Canopica recurring CI failure

`canopica-task-checkpoint` is the gate *before* a push. This is the procedure
*after* a red run whose symptom is not new — the same error string as
last time, or a failure a previous commit was supposed to have fixed.

It exists because one failure ("Memory Circuit Breaker is open") consumed
**five** round trips across two separate sessions, and every round but
the last was spent proposing a fix for a component that had not been
shown to be the failing one. The rule below is the whole lesson.

## 1. Can you name the exact component that failed? If not, stop.

Not "memory pressure" — *which* breaker, *which* limit, *what* was the
measured value against it. If the log does not say, **the next commit
adds diagnostics, not a fix.** A fix aimed at an unattributed cause is a
guess, and a guess that happens to go green teaches you something false.

This is not a counsel of perfection; it is the cheapest available move.
Diagnostics are behavior-neutral, so shipping them costs one run and
cannot break anything — whereas a wrong fix costs the same run *and*
leaves a misleading comment in the tree explaining a cause that was never
real.

The payoff, measured: `ai-eval` had gone red three times unattributably.
One commit of diagnostics resolved it on the very next red run, from the
log alone, with no further guessing.

## 2. Diagnostics parity: does the failing job have what its siblings have?

The reason the log did not say is usually not that nobody thought about
it — it is that a *newer* job never inherited the diagnostic steps an
*older* sibling accumulated, one incident at a time.

`e2e-ai` had a `df -h` baseline, a post-run `docker stats`, a
breaker/heap dump on failure, and a compose-log artifact. `ai-eval`,
written later against the same infrastructure, had **none of them** — so
identical failures were richly diagnosable in one job and completely
opaque in the other.

So: when a job fails opaquely, diff its steps against the sibling job
that uses the same services before doing anything else. Port what's
missing. This is the same drift `canopica-task-checkpoint`'s step 5 catches
from the other direction — there, code grew a dependency a job lacked;
here, a job lacked the diagnostics its siblings had. Both are
"true when written, silently invalidated later."

## 3. Distinguish a threshold from a distribution

Before tuning any threshold a second time, ask what the underlying metric
*does over time*. If it sawtooths, no threshold fixes it — you are moving
the dice, not loading them.

JVM heap under GC is the worked example: it climbs to near the top of
whatever heap it is given, then collapses on collection. Raising
ml-commons' threshold 85 → 92 did not fix that and could not have; the
real evidence was a GC logged 3s after the failure and a heap reading of
**18%** one second later. The garbage was never pressure.

**A threshold breached by a transient peak is a signal to handle, not a
limit to raise.** Which leads to:

## 4. Prefer handling the signal over raising the limit

An HTTP 429 is by definition "retry shortly" — from OpenSearch's
ml-commons breaker, from OpenRouter's rate limiter, from anything.
Treating it as fatal is the bug; retrying it is the fix. Raising the
limit so the signal stops firing removes the protection *and* leaves the
transient condition unhandled in production.

Two guardrails, both worth a test each, so "retry" never quietly becomes
"suppress":

- a condition that **never clears must still fail** the gate — a CI
  signal is only worth having if it can still go red;
- a **non-retryable error must still propagate on the first attempt** —
  otherwise a real bug gets dressed up as congestion and reported
  several seconds late.

## 5. Record what the evidence ruled *out*, not just what it confirmed

In `docs/STATUS.md`'s verification-log row, state which hypotheses died
and to what measurement — "every core breaker reported `tripped: 0`, so
this is ml-commons' and not OpenSearch's" is worth more to the next
reader than the conclusion alone. A future session with the same symptom
otherwise re-runs the same eliminations from scratch, which is exactly
what this skill exists to stop.

Note honestly when a fix is *credible* rather than *proven*. One green
run after a behavior-changing fix is weak evidence when the failure was
intermittent to begin with; say so in the row rather than recording a
guess as a fact.
