package canopica.api.fraud;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FraudRiskScoreRepository extends JpaRepository<FraudRiskScore, UUID> {

    Optional<FraudRiskScore> findByDeterminationId(UUID determinationId);
}
