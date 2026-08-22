package canopica.portal.repo;

import canopica.portal.domain.CaseAssignment;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CaseAssignmentRepository extends JpaRepository<CaseAssignment, UUID> {

    // Ordered newest-first so a same-day reassignment (old row's effective_to and the new row's
    // effective_from can legitimately both equal "today") resolves deterministically to the most recently
    // created row, rather than depending on whatever order Postgres happens to return -- see
    // CaseAssignmentService.reassign.
    @Query("""
        select a from CaseAssignment a
        where a.householdId = :householdId
          and a.effectiveFrom <= :asOf
          and (a.effectiveTo is null or a.effectiveTo >= :asOf)
        order by a.effectiveFrom desc, a.createdAt desc
        """)
    List<CaseAssignment> findEffectiveOn(
            @Param("householdId") UUID householdId, @Param("asOf") LocalDate asOf);

    @Modifying
    @Query("update CaseAssignment a set a.effectiveTo = :effectiveTo where a.id = :id")
    void endAssignment(@Param("id") UUID id, @Param("effectiveTo") LocalDate effectiveTo);
}
