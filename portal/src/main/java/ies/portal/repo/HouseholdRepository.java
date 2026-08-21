package ies.portal.repo;

import ies.portal.domain.Household;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface HouseholdRepository extends JpaRepository<Household, UUID> {
}
