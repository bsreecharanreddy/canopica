# Canopica — Policy-parameter-set supersession: closing an open-ended version

## 1. Why this exists

Phase 2 Task 3's rule-authoring copilot (Phase 2 design doc §2.3) ends in
a human accepting a proposal, at which point the API must **publish a
new `policy_parameter_set`**. That is the first code path in this system
that creates a parameter version at runtime — every set that exists today
was seeded by the `V4` migration.

Writing it surfaced a gap the settled decisions don't cover. Both of these
are already true and already right:

- **`policy_parameter_set` is effective-dated and immutable once
  published** (roadmap §3.5, STATUS.md's decisions table). `V3`'s trigger
  enforces it in the database: `before update or delete ... raise
  exception`, no exceptions.
- **The currently-in-force set is open-ended.** `V4` seeds `SNAP-FY2026`
  with `effective_to = null`, which is the honest representation — nobody
  has announced when it stops applying.

Together they make supersession impossible as the schema stands. A new set
starting 2026-10-01 would overlap `SNAP-FY2026`'s open range, and
`PolicyParameterSetRepository.findEffectiveOn` —

```java
where s.programCode = :programCode
  and s.effectiveFrom <= :asOf
  and (s.effectiveTo is null or s.effectiveTo >= :asOf)
```

— returns `Optional<PolicyParameterSet>`. Two matching rows is not "the
newer one wins"; it is an `IncorrectResultSizeDataAccessException` on the
next determination anyone runs. The failure lands on *determinations*, not
on the publish, which is the worst possible place for it.

This is not a relitigation of "immutable once published." It is the
question that decision never had to answer, because until Task 3 nothing
ever published a second set.

## 2. What is actually at stake

Worth being precise, because it turns out to be narrower than "immutability."

Reproducing an old determination (roadmap §3.5, points 2–4) runs through
`PolicyParameterResolver.resolveSnapByParameterSetId(UUID, int)` — the
determination stored the parameter-set **id** it used, and re-resolution
looks it up by that id and reads `policy_parameter` values. It never reads
`effective_from`, and it never reads `effective_to`.

So the reproducibility guarantee rests on exactly two things:

1. A published `policy_parameter` row's `numeric_value` never changes.
2. A `policy_parameter_set` row never disappears or changes identity.

`effective_to` participates in neither. Its only job is *selection* —
which set applies to a new determination on a given date. That distinction
is what makes this decidable rather than a genuine tension.

## 3. Options

### Option A — narrow the trigger to permit closing an open range

Keep `V3`'s refusal for every UPDATE except one: setting `effective_to`
from `null` to a date, with every other column bit-identical. Publishing
then closes the outgoing set the day before the new set starts, and ranges
stay non-overlapping.

```sql
-- V15, replacing V3's function body (the triggers themselves stay).
create or replace function policy_parameter_set_is_immutable() returns trigger
language plpgsql as $$
begin
    if tg_op = 'UPDATE'
       and old.effective_to is null
       and new.effective_to is not null
       and (new.id, new.program_code, new.version_label, new.effective_from,
            new.source_citation, new.retrieved_on)
           is not distinct from
           (old.id, old.program_code, old.version_label, old.effective_from,
            old.source_citation, old.retrieved_on)
    then
        return new;
    end if;
    raise exception 'policy_parameter_set rows are immutable once published (attempted %)', tg_op;
end;
$$;
```

`policy_parameter` keeps the blanket refusal unchanged — a published
*figure* stays absolutely immutable, which is the half reproducibility
actually rests on. The narrowing is one-way and one-shot: `null` → date is
allowed, date → anything is not, so a closed range can never be reopened
or moved.

- **For**: ranges stay non-overlapping, so the resolver keeps erroring on
  ambiguity instead of silently picking. The rule stays enforced by the
  database rather than by application convention, which is the property
  `PolicyParameterImmutabilityTest` exists to prove. The permitted edit is
  provably outside the reproducibility guarantee (§2).
- **Against**: "immutable once published" acquires an asterisk, and a
  reader has to read the trigger to learn what it is. Costs a migration.

### Option B — make the resolver prefer the newest matching set

Leave schema and trigger alone. Add `order by s.effectiveFrom desc limit
1` to `findEffectiveOn`, so an overlap resolves deterministically to the
most recently-starting set.

- **For**: one line, no migration, no touching a Phase 1a invariant.
  Standard slowly-changing-dimension read semantics.
- **Against**: overlapping ranges become silently legal. `effective_to`
  degrades to a documentation column that no longer constrains anything,
  and a genuine data error — two sets accidentally covering the same date
  — stops being detectable at read time. It trades a loud failure for a
  quiet wrong answer about a benefit amount, which is the wrong direction
  for this system.

### Option C — require the reviewer to supply a non-overlapping range

Refuse to publish when the incoming range would overlap an open-ended set.

Rejected outright: in the seeded state *every* publish overlaps, so the
accept path would never work. Listed only so it is on the record as
considered rather than missed.

## 4. Recommendation

**Option A.**

The deciding argument is §2: the edit Option A permits is provably
incapable of affecting determination reproducibility, because
re-derivation resolves by parameter-set id and never reads either date
column. Option B's cost lands somewhere much worse — it removes the
system's ability to notice that two parameter versions claim the same
date, on the one table where being quietly wrong means a wrong benefit
amount.

Option A also keeps the invariant where this repo has consistently put
invariants: in the database, not in a service class. The narrowing is
written as a condition the database checks, so "you may close an open
range, once, and change nothing else" is enforced rather than documented.

## 5. Consequences if adopted

- New migration `V15__policy_parameter_set_closeable.sql` replacing the
  trigger *function* body. The triggers themselves, and
  `policy_parameter`'s own trigger, are untouched.
- `PolicyParameterPublishService`'s accept path closes the outgoing set at
  `newEffectiveFrom - 1 day` inside the same transaction that inserts the
  new set, so there is no window where two open sets exist.
- `PolicyParameterImmutabilityTest` gains cases for the new boundary: a
  `null` → date close succeeds; a date → different-date move is refused; a
  close that also edits another column is refused; `policy_parameter` is
  still refused outright.
- The reviewer supplies `versionLabel`, `effectiveFrom` and
  `sourceCitation` when accepting. These cannot be derived — an effective
  date is a policy fact from the memo, not something to infer — and
  `version_label` is `unique`, so it has to be a human's choice.
- A new set is **complete**, not a delta: it copies every
  `policy_parameter` row from the outgoing set and applies the accepted
  proposal's changes over the top. `PolicyParameterResolver` requires the
  full parameter list to build a `SnapPolicyParameters`, so a partial set
  would resolve to a `PolicyParameterNotFoundException` rather than to a
  wrong number — but it would still be a broken publish.

## 6. Not an AI design decision

Recorded explicitly so a later reader doesn't wonder why the
`canopica-ai-design-review` pass was skipped: this decision is entirely about
the relational model's temporality semantics. It is *occasioned* by an AI
capability, but nothing about it changes if the proposal on the reviewer's
screen was drafted by a model, typed by a human, or parsed from a
spreadsheet. The AI-boundary questions for the copilot itself were settled
in Phase 2 design doc §2.3 and are unaffected.
