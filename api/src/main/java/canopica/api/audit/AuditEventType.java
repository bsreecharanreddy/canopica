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
    NOTICE_SENT,
    /**
     * A determination's fraud-risk score cleared the review threshold (Phase 4 Task 2). Written by the
     * Python worker's {@code fraud_scoring_consumer.py} via a raw {@code insert}, never by this module's own
     * {@link AuditService} -- same reasoning as {@link #DOCUMENT_CLASSIFIED}'s own doc comment: {@link
     * JdbcAuditService#findBySubject} deserializes {@code event_type} back into this enum on every read, and
     * a below-threshold score is still recorded in {@code fraud_risk_score} but never raises this event.
     */
    FRAUD_FLAG_RAISED,
    /**
     * A supervisor decided a raised fraud flag (Phase 4 Task 3) -- {@code CONFIRMED_RISK} or {@code CLEARED}
     * in the payload. Written by {@link canopica.api.fraud.FraudReviewService}, this module's own {@link
     * AuditService}, unlike {@link #FRAUD_FLAG_RAISED}: the review decision is Java's own write, not the
     * worker's.
     */
    FRAUD_FLAG_REVIEWED,
    /**
     * A sampled QC re-derivation produced a nonzero diff against the original {@code benefit_amount}
     * (Phase 4 Task 4). Written by the Python worker's {@code qc_summary_consumer.py} via a raw
     * {@code update}/{@code insert}, never by this module's own {@link AuditService} -- same reasoning as
     * {@link #DOCUMENT_CLASSIFIED}'s own doc comment: {@link JdbcAuditService#findBySubject} deserializes
     * {@code event_type} back into this enum on every read, and a zero-diff sampled case is still recorded in
     * {@code payment_error_review} but never raises this event.
     */
    QC_DISCREPANCY_FLAGGED
}
