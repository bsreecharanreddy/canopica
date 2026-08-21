package canopica.portal.repo;

import canopica.portal.domain.Verification;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VerificationRepository extends JpaRepository<Verification, UUID> {
}
