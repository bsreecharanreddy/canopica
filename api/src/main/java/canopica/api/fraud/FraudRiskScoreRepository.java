package canopica.api.fraud;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FraudRiskScoreRepository extends JpaRepository<FraudRiskScore, UUID> {

    Optional<FraudRiskScore> findByDeterminationId(UUID determinationId);

    /** Task 3's review queue: unreviewed flags, highest risk first ({@code fraud_risk_score_review_queue_idx}, V23). */
    List<FraudRiskScore> findByReviewOutcomeIsNullOrderByScoreDesc();
}
