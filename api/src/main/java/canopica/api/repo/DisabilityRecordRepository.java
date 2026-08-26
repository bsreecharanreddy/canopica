package canopica.api.repo;

import canopica.api.domain.DisabilityRecord;
import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DisabilityRecordRepository extends JpaRepository<DisabilityRecord, UUID> {

    @Query("""
        select d from DisabilityRecord d
        where d.personId in :personIds
          and d.effectiveFrom <= :asOf
          and (d.effectiveTo is null or d.effectiveTo >= :asOf)
        """)
    List<DisabilityRecord> findEffectiveOn(
            @Param("personIds") Collection<UUID> personIds, @Param("asOf") LocalDate asOf);
}
