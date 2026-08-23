package ies.portal.repo;

import ies.portal.domain.ResourceRecord;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ResourceRecordRepository extends JpaRepository<ResourceRecord, UUID> {

    @Query("""
        select r from ResourceRecord r
        where r.householdId = :householdId
          and r.effectiveFrom <= :asOf
          and (r.effectiveTo is null or r.effectiveTo >= :asOf)
        """)
    List<ResourceRecord> findEffectiveOn(
            @Param("householdId") UUID householdId, @Param("asOf") LocalDate asOf);
}
