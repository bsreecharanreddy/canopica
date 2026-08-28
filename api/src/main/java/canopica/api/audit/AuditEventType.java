package canopica.api.audit;

/** Mirrors the {@code audit_event.event_type} CHECK constraint (V6 migration, widened by V16). */
public enum AuditEventType {
    APPLICATION_SUBMITTED,
    DETERMINATION_MADE,
    CASE_VIEWED,
    VERIFICATION_UPDATED,
    /**
     * A human accepted a rule-authoring proposal and a new parameter set went into force. The
     * {@code policy_parameter_proposal} row records the same fact, but that table is mutable by design, so
     * the tamper-evident answer to "who published this figure" has to live in the chain (roadmap §3.6).
     */
    POLICY_PARAMETER_PUBLISHED,
    /** A document was uploaded against a program request (Phase 3 design doc §2.6). Keyed on {@code
     * "program_request"}, same as {@link #APPLICATION_SUBMITTED}. */
    DOCUMENT_UPLOADED,
    /**
     * A document finished classification/extraction (Phase 3 Task 3). Written by the Python worker's
     * {@code document_intake_consumer.py} via a raw {@code insert}, never by this module's own {@link
     * AuditService} -- the trigger that computes the hash chain (V6 migration) doesn't care which process
     * appends the row, so no Java-side writer is needed. Listed here anyway because {@link
     * JdbcAuditService#findBySubject} deserializes {@code event_type} back into this enum on every read, and
     * the case audit-trail endpoint would throw on an unrecognized value the first time a document was
     * actually classified.
     */
    DOCUMENT_CLASSIFIED,
    /**
     * A determination's own correspondence was drafted (Phase 3 Task 5). Written by the Python worker's
     * {@code correspondence_consumer.py} via a raw {@code insert}, never by this module's own {@link
     * AuditService} -- same reasoning as {@link #DOCUMENT_CLASSIFIED}'s own doc comment: {@link
     * JdbcAuditService#findBySubject} deserializes {@code event_type} back into this enum on every read.
     */
    NOTICE_DRAFTED,
    /**
     * A worker approved an AI-drafted notice and its content was rendered to PDF (Phase 3 Task 6). Appended
     * by {@link canopica.api.notice.NoticeService#approve} in the same transaction as {@link #NOTICE_SENT},
     * immediately before it -- a notice never sits in an APPROVED-but-not-yet-SENT state here (design doc
     * §2.4's "dispatch" is generated, never actually delivered, per the tradeoffs doc's unrevisited §4.4), so
     * the two events always appear together, in this order.
     */
    NOTICE_APPROVED,
    /**
     * The same approval action recorded as "sent" (Phase 3 Task 6) -- see {@link #NOTICE_APPROVED}'s own doc
     * comment for why these two always appear as a pair.
     */
    NOTICE_SENT
}
