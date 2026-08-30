package canopica.api.api.dto;

import canopica.api.fraud.FraudRiskScore;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * One review-queue row, or a confirm/clear response (Phase 4 Task 3). {@code topContributingFeatures} is
 * passed through as {@link JsonNode} rather than a typed field -- the same "don't re-map a nested blob into a
 * typed DTO" convention {@link NoticeReviewItemResponse} already established for {@code validationResult},
 * so the review UI can show each feature's name/value/z-score with no second endpoint.
 */
public record FraudRiskScoreResponse(
        UUID id, UUID programRequestId, UUID determinationId, BigDecimal score,
        JsonNode topContributingFeatures, String modelVersion, Instant scoredAt,
        String reviewOutcome, String reviewedBy, Instant reviewedAt) {

    public static FraudRiskScoreResponse from(FraudRiskScore fraudRiskScore, JsonNode topContributingFeatures) {
        return new FraudRiskScoreResponse(
                fraudRiskScore.getId(), fraudRiskScore.getProgramRequestId(), fraudRiskScore.getDeterminationId(),
                fraudRiskScore.getScore(), topContributingFeatures, fraudRiskScore.getModelVersion(),
                fraudRiskScore.getScoredAt(), fraudRiskScore.getReviewOutcome(), fraudRiskScore.getReviewedBy(),
                fraudRiskScore.getReviewedAt());
    }
}
