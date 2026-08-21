package canopica.portal.repo;

import canopica.portal.domain.ProgramRequest;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProgramRequestRepository extends JpaRepository<ProgramRequest, UUID> {

    List<ProgramRequest> findByApplicationId(UUID applicationId);

    @Query("select r from ProgramRequest r where r.applicationId in "
            + "(select a.id from Application a where a.householdId = :householdId)")
    List<ProgramRequest> findByHouseholdId(@Param("householdId") UUID householdId);
}
