package ies.portal.repo;

import ies.portal.domain.Verification;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface VerificationRepository extends JpaRepository<Verification, UUID> {

    List<Verification> findByProgramRequestId(UUID programRequestId);

    @Modifying
    @Query("update Verification v set v.status = :status, v.satisfiedOn = :satisfiedOn where v.id = :id")
    void updateStatus(@Param("id") UUID id, @Param("status") String status, @Param("satisfiedOn") LocalDate satisfiedOn);
}
