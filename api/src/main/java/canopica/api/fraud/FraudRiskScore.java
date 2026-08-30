package canopica.api.fraud;

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
 * One determination's fraud-risk score (Phase 4 design doc §2.2/§2.8). The row itself is written by the
 * Python worker's {@code fraud_scoring_consumer.py} via a raw insert, the same split {@code
 * document.extraction} and {@code notice.content} already establish -- Java never computes a score. Task 3
 * adds the human review decision as intent-named transitions rather than setters, the same reasoning {@link
 * canopica.api.notice.Notice}'s own doc comment gives -- no code path can mark a flag reviewed twice or set
 * an outcome with no reviewer attribution.
 */
@Entity
@Table(name = "fraud_risk_score")
public class FraudRiskScore {

    @Id
    private UUID id;

    @Column(name = "program_request_id", nullable = false)
    private UUID programRequestId;

    @Column(name = "determination_id", nullable = false)
    private UUID determinationId;

    @Column(name = "score", nullable = false)
    private BigDecimal score;

    @Column(name = "top_contributing_features", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String topContributingFeatures;

    @Column(name = "model_version", nullable = false)
    private String modelVersion;

    @Column(name = "scored_at", insertable = false, updatable = false)
    private Instant scoredAt;

    @Column(name = "reviewed_by")
    private String reviewedBy;

    @Column(name = "reviewed_at")
    private Instant reviewedAt;

    @Column(name = "review_outcome")
    private String reviewOutcome;

    protected FraudRiskScore() {
        // JPA
    }

    public FraudRiskScore(UUID id, UUID programRequestId, UUID determinationId, BigDecimal score,
                           String topContributingFeatures, String modelVersion) {
        this.id = id;
        this.programRequestId = programRequestId;
        this.determinationId = determinationId;
        this.score = score;
        this.topContributingFeatures = topContributingFeatures;
        this.modelVersion = modelVersion;
    }

    /**
     * Phase 4 Task 3: a supervisor confirmed this flag reflects a real risk worth further, out-of-band
     * investigation. Never touches the determination, the benefit amount, or any notice (constraint 19) --
     * this is a case-management fact about the flag itself, nothing else.
     */
    public void confirmRisk(String reviewedBy, Instant now) {
        requireUnreviewed();
        this.reviewOutcome = "CONFIRMED_RISK";
        this.reviewedBy = reviewedBy;
        this.reviewedAt = now;
    }

    /** A supervisor reviewed the flag and found nothing warranting further action. */
    public void clear(String reviewedBy, Instant now) {
        requireUnreviewed();
        this.reviewOutcome = "CLEARED";
        this.reviewedBy = reviewedBy;
        this.reviewedAt = now;
    }

    /** A second reviewer must not be able to re-decide an already-reviewed flag. */
    private void requireUnreviewed() {
        if (reviewOutcome != null) {
            throw new IllegalStateException("fraud_risk_score " + id + " was already reviewed (" + reviewOutcome + ")");
        }
    }

    public UUID getId() {
        return id;
    }

    public UUID getProgramRequestId() {
        return programRequestId;
    }

    public UUID getDeterminationId() {
        return determinationId;
    }

    public BigDecimal getScore() {
        return score;
    }

    public String getTopContributingFeatures() {
        return topContributingFeatures;
    }

    public String getModelVersion() {
        return modelVersion;
    }

    public Instant getScoredAt() {
        return scoredAt;
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
