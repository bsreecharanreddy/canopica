package canopica.api.api.dto;

import canopica.api.qc.PaymentErrorReview;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * One review-queue row, or a confirm/dismiss response (Phase 4 Task 5). {@code reproducedTrace} is
 * deliberately excluded -- it exists only for {@code ai/qc_assistant}'s own grounding check (constraint 21),
 * not for a human reviewer to read raw DMN trace JSON.
 */
public record PaymentErrorReviewResponse(
        UUID id, UUID determinationId, BigDecimal originalAmount, BigDecimal reproducedAmount,
        BigDecimal errorAmount, String aiSummary, Instant sampledAt,
        String reviewOutcome, String reviewedBy, Instant reviewedAt) {

    public static PaymentErrorReviewResponse from(PaymentErrorReview review) {
        return new PaymentErrorReviewResponse(
                review.getId(), review.getDeterminationId(), review.getOriginalAmount(), review.getReproducedAmount(),
                review.getErrorAmount(), review.getAiSummary(), review.getSampledAt(),
                review.getReviewOutcome(), review.getReviewedBy(), review.getReviewedAt());
    }
}
