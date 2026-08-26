package canopica.api.repo;

import canopica.api.domain.Person;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository extends JpaRepository<Person, UUID> {

    // Plural: the same real citizen submitting more than once over time legitimately produces more than
    // one person row carrying their subject (see Person.keycloakSubject's own javadoc).
    List<Person> findByKeycloakSubject(String keycloakSubject);
}
