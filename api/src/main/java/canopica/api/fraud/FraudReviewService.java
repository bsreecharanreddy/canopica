package canopica.api.fraud;

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
 * Owns the one thing Java writes to {@code fraud_risk_score}: the human review decision (Phase 4 Task 3).
 * Nothing else writes here -- the worker's {@code fraud_scoring_consumer.py} inserts the scored row directly,
 * the same split {@link canopica.api.notice.NoticeService}'s own doc comment establishes for {@code notice}.
 */
@Service
public class FraudReviewService {

    private final FraudRiskScoreRepository scores;
    private final AuditService auditService;
    private final Clock clock;

    FraudReviewService(FraudRiskScoreRepository scores, AuditService auditService, Clock clock) {
        this.scores = scores;
        this.auditService = auditService;
        this.clock = clock;
    }

    public FraudRiskScore findById(UUID scoreId) {
        return scores.findById(scoreId)
                .orElseThrow(() -> new NoSuchElementException("no fraud_risk_score with id " + scoreId));
    }

    @Transactional
    public FraudRiskScore confirmRisk(UUID scoreId, String reviewedBy) {
        FraudRiskScore score = findById(scoreId);
        score.confirmRisk(reviewedBy, clock.instant());
        FraudRiskScore saved = scores.save(score);
        appendReviewedEvent(saved, reviewedBy);
        return saved;
    }

    @Transactional
    public FraudRiskScore clear(UUID scoreId, String reviewedBy) {
        FraudRiskScore score = findById(scoreId);
        score.clear(reviewedBy, clock.instant());
        FraudRiskScore saved = scores.save(score);
        appendReviewedEvent(saved, reviewedBy);
        return saved;
    }

    private void appendReviewedEvent(FraudRiskScore score, String reviewedBy) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("fraud_risk_score_id", score.getId().toString());
        payload.put("review_outcome", score.getReviewOutcome());
        auditService.append(
                AuditEventType.FRAUD_FLAG_REVIEWED, reviewedBy, "eligibility_determination",
                score.getDeterminationId(), payload);
    }
}
