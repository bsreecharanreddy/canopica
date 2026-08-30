package canopica.api.api;

import canopica.api.api.dto.FraudRiskScoreResponse;
import canopica.api.fraud.FraudReviewService;
import canopica.api.fraud.FraudRiskScore;
import canopica.api.fraud.FraudRiskScoreRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Fraud-risk review queue, confirm, and clear (Phase 4 Task 3). {@code SecurityConfig} restricts all of
 * {@code /api/fraud/**} to the SUPERVISOR role -- there is no additional in-controller role check to
 * duplicate, and no caseload scoping either: unlike {@link NoticeController}'s own per-worker review queue,
 * this is a cross-caseload triage queue a supervisor works from directly (design doc §2.9's "reuses this
 * role's existing 'view any case' scope" -- no new Keycloak role). Neither {@code confirm} nor {@code clear}
 * ever touches {@code eligibility_determination}, the benefit amount, or any notice (constraint 19) -- the
 * review outcome is a case-management fact about the flag itself, nothing else.
 */
@RestController
class FraudReviewController {

    private final FraudRiskScoreRepository scores;
    private final FraudReviewService fraudReviewService;
    private final ObjectMapper objectMapper;

    FraudReviewController(
            FraudRiskScoreRepository scores, FraudReviewService fraudReviewService, ObjectMapper objectMapper) {
        this.scores = scores;
        this.fraudReviewService = fraudReviewService;
        this.objectMapper = objectMapper;
    }

    @GetMapping("/api/fraud/review-queue")
    List<FraudRiskScoreResponse> reviewQueue() {
        return scores.findByReviewOutcomeIsNullOrderByScoreDesc().stream()
                .map(score -> FraudRiskScoreResponse.from(score, readTopContributingFeatures(score)))
                .toList();
    }

    @PostMapping("/api/fraud/{scoreId}/confirm")
    FraudRiskScoreResponse confirm(@PathVariable UUID scoreId, Authentication authentication) {
        FraudRiskScore score = fraudReviewService.confirmRisk(scoreId, authentication.getName());
        return FraudRiskScoreResponse.from(score, readTopContributingFeatures(score));
    }

    @PostMapping("/api/fraud/{scoreId}/clear")
    FraudRiskScoreResponse clear(@PathVariable UUID scoreId, Authentication authentication) {
        FraudRiskScore score = fraudReviewService.clear(scoreId, authentication.getName());
        return FraudRiskScoreResponse.from(score, readTopContributingFeatures(score));
    }

    private JsonNode readTopContributingFeatures(FraudRiskScore score) {
        try {
            return objectMapper.readTree(score.getTopContributingFeatures());
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "failed to parse stored top_contributing_features JSON for fraud_risk_score " + score.getId(), e);
        }
    }
}
