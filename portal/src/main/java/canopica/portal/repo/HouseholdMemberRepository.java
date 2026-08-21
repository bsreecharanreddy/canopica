package canopica.portal.repo;

import canopica.portal.domain.HouseholdMember;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface HouseholdMemberRepository extends JpaRepository<HouseholdMember, UUID> {

    @Query("""
        select m from HouseholdMember m
        where m.householdId = :householdId
          and m.effectiveFrom <= :asOf
          and (m.effectiveTo is null or m.effectiveTo >= :asOf)
        """)
    List<HouseholdMember> findEffectiveOn(
            @Param("householdId") UUID householdId, @Param("asOf") LocalDate asOf);
}
