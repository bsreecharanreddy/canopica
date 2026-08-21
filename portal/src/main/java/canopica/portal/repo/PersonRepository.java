package canopica.portal.repo;

import canopica.portal.domain.Person;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository extends JpaRepository<Person, UUID> {
}
