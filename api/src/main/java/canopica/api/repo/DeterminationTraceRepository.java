package canopica.api.repo;

import canopica.api.domain.DeterminationTrace;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DeterminationTraceRepository extends JpaRepository<DeterminationTrace, UUID> {

    Optional<DeterminationTrace> findByDeterminationId(UUID determinationId);
}
