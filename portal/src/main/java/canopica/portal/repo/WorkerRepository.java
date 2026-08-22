package canopica.portal.repo;

import canopica.portal.domain.Worker;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WorkerRepository extends JpaRepository<Worker, UUID> {

    Optional<Worker> findByKeycloakSubject(String keycloakSubject);
}
