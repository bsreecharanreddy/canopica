# New Application Processing

## Initial intake review

When a new SNAP application arrives (`APPLICATION_SUBMITTED`), open the
case detail page and confirm the household composition, income, and
expense records the applicant entered match what they described in any
attached documents. Do not request additional documents the applicant has
already provided in a legible, verifiable form -- re-requesting a document
already on file delays the case without adding new information.

## Expedited service screening

Every new application is automatically screened for expedited eligibility
at intake (gross monthly income under the expedited threshold, or very
low liquid resources, or a migrant/seasonal farmworker household with
minimal resources). If `program_request.is_expedited` is true, the case
must reach a determination within 7 calendar days of the request date,
not the standard 30. Check the at-risk case queue's own days-remaining
figure before assuming a case has the standard runway -- an expedited
case shows far less slack than its submission date alone would suggest.

## Outstanding verification checklist

A new application typically opens with an `INCOME` verification in
`OUTSTANDING` status, and may carry `IDENTITY`, `RESIDENCY`,
`SHELTER_COST`, `MEDICAL_EXPENSE`, `DISABILITY`, or
`HOUSEHOLD_COMPOSITION` verifications depending on what the household
reported. Work outstanding verifications in the order they block a
determination: identity and residency first (categorical gatekeepers),
then income (drives the actual benefit calculation), then any deduction-
supporting verification (shelter cost, medical expense) last, since a
missing deduction verification narrows the benefit amount but does not by
itself block eligibility.

## Requesting verification from the applicant

Use the verification request flow rather than an out-of-band phone call
or email whenever possible -- every request and resolution is logged as a
`VERIFICATION_UPDATED` audit event pair (`REQUESTED` then `RECEIVED`),
which is what lets a supervisor reconstruct the full verification history
on review. A verification with no logged request is a verification with
no evidence it was ever properly asked for.

## Running the determination

Once every verification a case needs to reach a decision is `RECEIVED` or
`WAIVED`, run the determination. The rules engine evaluates the
household's current, effective-dated facts against the currently
in-force policy parameter set -- it does not ask the caseworker to
compute anything by hand, and its own persisted trace is what the case
audit trail and any later QC re-derivation both rely on. A determination
already made is never edited in place; a corrected fact set produces a
new determination, not a changed old one.

## Notifying the applicant

Once a determination is decided, an AI-drafted notice is queued
automatically. Review the drafted notice's content against the real
determination it explains before approving it -- the draft is advisory
only, and approving it is what actually renders and sends the notice to
the applicant. Never approve a notice whose stated benefit amount or
reason code doesn't match the determination it's paired with.
