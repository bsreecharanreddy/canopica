package canopica.api.repo;

import canopica.api.domain.VerificationResponse;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VerificationResponseRepository extends JpaRepository<VerificationResponse, UUID> {

    Optional<VerificationResponse> findByVerificationId(UUID verificationId);
}
