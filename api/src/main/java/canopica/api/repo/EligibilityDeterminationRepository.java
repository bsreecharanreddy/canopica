package canopica.api.repo;

import canopica.api.domain.EligibilityDetermination;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EligibilityDeterminationRepository extends JpaRepository<EligibilityDetermination, UUID> {

    List<EligibilityDetermination> findByProgramRequestIdOrderByDecidedAtDesc(UUID programRequestId);
}
