package canopica.api.qc;

import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Owns the one thing Java writes to {@code payment_error_review} after sampling: the human review decision
 * (Phase 4 Task 5). Nothing else writes here -- {@link QcSamplingService} inserts the sampled row and the
 * worker's {@code qc_summary_consumer.py} fills in {@code ai_summary}, the same three-way split {@link
 * canopica.api.fraud.FraudReviewService}'s own doc comment describes for {@code fraud_risk_score}.
 */
@Service
public class QcReviewService {

    private final PaymentErrorReviewRepository reviews;
    private final AuditService auditService;
    private final Clock clock;

    QcReviewService(PaymentErrorReviewRepository reviews, AuditService auditService, Clock clock) {
        this.reviews = reviews;
        this.auditService = auditService;
        this.clock = clock;
    }

    public PaymentErrorReview findById(UUID reviewId) {
        return reviews.findById(reviewId)
                .orElseThrow(() -> new NoSuchElementException("no payment_error_review with id " + reviewId));
    }

    @Transactional
    public PaymentErrorReview confirmError(UUID reviewId, String reviewedBy) {
        PaymentErrorReview review = findById(reviewId);
        review.confirmError(reviewedBy, clock.instant());
        PaymentErrorReview saved = reviews.save(review);
        appendReviewCompletedEvent(saved, reviewedBy);
        return saved;
    }

    @Transactional
    public PaymentErrorReview dismiss(UUID reviewId, String reviewedBy) {
        PaymentErrorReview review = findById(reviewId);
        review.dismiss(reviewedBy, clock.instant());
        PaymentErrorReview saved = reviews.save(review);
        appendReviewCompletedEvent(saved, reviewedBy);
        return saved;
    }

    private void appendReviewCompletedEvent(PaymentErrorReview review, String reviewedBy) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("payment_error_review_id", review.getId().toString());
        payload.put("review_outcome", review.getReviewOutcome());
        auditService.append(
                AuditEventType.QC_REVIEW_COMPLETED, reviewedBy, "eligibility_determination",
                review.getDeterminationId(), payload);
    }
}
