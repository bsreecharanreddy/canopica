package canopica.portal.repo;

import canopica.portal.domain.VerificationResponse;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VerificationResponseRepository extends JpaRepository<VerificationResponse, UUID> {

    Optional<VerificationResponse> findByVerificationId(UUID verificationId);
}
