package canopica.api.repo;

import canopica.api.domain.ProgramRequest;
import java.time.LocalDate;
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

    /**
     * Every program request belonging to a household {@code workerId} currently holds an active {@code
     * case_assignment} for -- the Caseworker Dashboard's own caseload, not {@code /api/worker/cases}'s
     * unscoped list of every case in the system (that endpoint applies no caseload filter at all today).
     */
    @Query("""
        select r from ProgramRequest r where r.applicationId in (
            select a.id from Application a where a.householdId in (
                select ca.householdId from CaseAssignment ca
                where ca.workerId = :workerId
                  and ca.effectiveFrom <= :asOf
                  and (ca.effectiveTo is null or ca.effectiveTo >= :asOf)
            )
        )
        """)
    List<ProgramRequest> findByAssignedWorker(@Param("workerId") UUID workerId, @Param("asOf") LocalDate asOf);
}
