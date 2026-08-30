package canopica.api.qc;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * One sampled determination's QC re-derivation result (Phase 4 design doc §2.3/Task 4). Unlike {@code
 * fraud_risk_score}, this row is written by Java itself ({@link QcSamplingService}) -- {@code reproduce()}
 * only runs in the JVM (DMN evaluation is Java-only) -- and {@code ai_summary} is what the Python worker's
 * {@code qc_summary_consumer.py} fills in afterward via a raw update, the reverse split {@link
 * canopica.api.fraud.FraudRiskScore}'s own doc comment describes for that table. Task 5 adds the human review
 * decision as intent-named transitions, same reasoning as that class.
 */
@Entity
@Table(name = "payment_error_review")
public class PaymentErrorReview {

    @Id
    private UUID id;

    @Column(name = "determination_id", nullable = false)
    private UUID determinationId;

    @Column(name = "original_amount", nullable = false)
    private BigDecimal originalAmount;

    @Column(name = "reproduced_amount", nullable = false)
    private BigDecimal reproducedAmount;

    @Column(name = "error_amount", nullable = false)
    private BigDecimal errorAmount;

    @Column(name = "reproduced_trace", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String reproducedTrace;

    @Column(name = "ai_summary")
    private String aiSummary;

    @Column(name = "sampled_at", insertable = false, updatable = false)
    private Instant sampledAt;

    @Column(name = "reviewed_by")
    private String reviewedBy;

    @Column(name = "reviewed_at")
    private Instant reviewedAt;

    @Column(name = "review_outcome")
    private String reviewOutcome;

    protected PaymentErrorReview() {
        // JPA
    }

    public PaymentErrorReview(UUID id, UUID determinationId, BigDecimal originalAmount,
                               BigDecimal reproducedAmount, BigDecimal errorAmount, String reproducedTrace) {
        this.id = id;
        this.determinationId = determinationId;
        this.originalAmount = originalAmount;
        this.reproducedAmount = reproducedAmount;
        this.errorAmount = errorAmount;
        this.reproducedTrace = reproducedTrace;
    }

    public UUID getId() {
        return id;
    }

    public UUID getDeterminationId() {
        return determinationId;
    }

    public BigDecimal getOriginalAmount() {
        return originalAmount;
    }

    public BigDecimal getReproducedAmount() {
        return reproducedAmount;
    }

    public BigDecimal getErrorAmount() {
        return errorAmount;
    }

    public String getReproducedTrace() {
        return reproducedTrace;
    }

    public String getAiSummary() {
        return aiSummary;
    }

    public Instant getSampledAt() {
        return sampledAt;
    }

    public String getReviewedBy() {
        return reviewedBy;
    }

    public Instant getReviewedAt() {
        return reviewedAt;
    }

    public String getReviewOutcome() {
        return reviewOutcome;
    }
}
