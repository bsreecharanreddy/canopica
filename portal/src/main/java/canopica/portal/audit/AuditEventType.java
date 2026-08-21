package canopica.portal.audit;

/** Mirrors the {@code audit_event.event_type} CHECK constraint (V6 migration). */
public enum AuditEventType {
    APPLICATION_SUBMITTED,
    DETERMINATION_MADE,
    CASE_VIEWED,
    VERIFICATION_UPDATED
}
