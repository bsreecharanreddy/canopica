package ies.portal.repo;

import ies.portal.domain.Household;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface HouseholdRepository extends JpaRepository<Household, UUID> {

    @Modifying
    @Query("update Household h set h.isSensitive = :isSensitive, h.sensitiveReason = :sensitiveReason where h.id = :id")
    void updateSensitivity(
            @Param("id") UUID id, @Param("isSensitive") boolean isSensitive, @Param("sensitiveReason") String sensitiveReason);
}
