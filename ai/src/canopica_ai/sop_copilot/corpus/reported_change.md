# Reported Change Processing

## What counts as a reportable change

A household must report a change in income, household composition,
shelter cost, or resources once it occurs -- the case does not wait for
the next scheduled renewal to reflect it. A reported income change is
recorded as a new, effective-dated income record rather than a correction
to the existing one, so the case retains a full history of what the
household's income actually was at each point in time, not just its
current value.

## Income changes

When a household reports a new or changed income amount, add it as a new
income record effective from the date the change actually took effect,
not the date it was reported. Do not end-date or delete the prior income
record -- the determination's own reproducibility guarantee depends on
every past fact still being queryable exactly as it stood on the date of
a past decision. If the change plausibly affects the current benefit
amount, a new income verification should be opened rather than assumed
satisfied by the household's own unverified report.

## Household composition changes

A person added to or removed from a household (a birth, a household
member moving out, a marriage) changes the effective household size the
rules engine evaluates against. Composition changes are entered as a new
household-member record effective from the date of the change, mirroring
how income changes are handled -- the case's past composition remains
queryable, it is not overwritten. A composition change alone is grounds
to open a `HOUSEHOLD_COMPOSITION` verification if the household did not
already provide supporting documentation.

## Re-verification after a reported change

Not every reported change requires re-running the full new-application
verification checklist. A shelter cost change only needs a
`SHELTER_COST` verification reopened; it does not require re-verifying
identity or residency, which do not change simply because a rent amount
did. Re-open only the verification types the specific reported change
actually affects.

## Re-determination

Once the affected verification is resolved, a new determination should
be run against the household's now-current facts. This produces a new,
separate determination record -- the prior determination remains in the
case's history exactly as it was decided, which is what makes a later QC
sample's re-derivation meaningful: it re-evaluates a specific past
determination against the parameter set that was actually in force when
that determination was made, not against today's parameters.

## Stall risk on a reported change

A reported change that sits with an outstanding verification for several
days without caseworker action is exactly the kind of case the SLA
at-risk queue surfaces, aged against the same 30-day (or 7-day expedited)
standard a new application uses. A reported change is not exempt from
the processing standard simply because the case was already open before
the change came in.
