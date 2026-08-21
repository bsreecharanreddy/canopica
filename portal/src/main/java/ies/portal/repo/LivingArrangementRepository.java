package ies.portal.repo;

import ies.portal.domain.LivingArrangement;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface LivingArrangementRepository extends JpaRepository<LivingArrangement, UUID> {

    @Query("""
        select a from LivingArrangement a
        where a.householdId = :householdId
          and a.effectiveFrom <= :asOf
          and (a.effectiveTo is null or a.effectiveTo >= :asOf)
        """)
    List<LivingArrangement> findEffectiveOn(
            @Param("householdId") UUID householdId, @Param("asOf") LocalDate asOf);
}
