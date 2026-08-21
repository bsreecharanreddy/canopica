package canopica.portal.repo;

import canopica.portal.domain.CaseAssignment;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CaseAssignmentRepository extends JpaRepository<CaseAssignment, UUID> {

    @Query("""
        select a from CaseAssignment a
        where a.householdId = :householdId
          and a.effectiveFrom <= :asOf
          and (a.effectiveTo is null or a.effectiveTo >= :asOf)
        """)
    List<CaseAssignment> findEffectiveOn(
            @Param("householdId") UUID householdId, @Param("asOf") LocalDate asOf);
}
