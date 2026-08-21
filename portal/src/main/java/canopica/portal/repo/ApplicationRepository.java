package canopica.portal.repo;

import canopica.portal.domain.Application;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ApplicationRepository extends JpaRepository<Application, UUID> {
}
