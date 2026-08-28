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
    DOCUMENT_CLASSIFIED
}
