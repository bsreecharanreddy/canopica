package ies.portal.repo;

import ies.portal.domain.PolicyParameterSet;
import java.time.LocalDate;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PolicyParameterSetRepository extends JpaRepository<PolicyParameterSet, UUID> {

    @Query("""
        select s from PolicyParameterSet s
        where s.programCode = :programCode
          and s.effectiveFrom <= :asOf
          and (s.effectiveTo is null or s.effectiveTo >= :asOf)
        """)
    Optional<PolicyParameterSet> findEffectiveOn(
            @Param("programCode") String programCode, @Param("asOf") LocalDate asOf);
}
