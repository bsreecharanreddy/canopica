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
    POLICY_PARAMETER_PUBLISHED
}
