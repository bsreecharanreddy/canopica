package ies.portal.repo;

import ies.portal.domain.EligibilityDetermination;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EligibilityDeterminationRepository extends JpaRepository<EligibilityDetermination, UUID> {
}
