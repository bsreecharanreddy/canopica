package canopica.portal.repo;

import canopica.portal.domain.IncomeRecord;
import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IncomeRecordRepository extends JpaRepository<IncomeRecord, UUID> {

    @Query("""
        select r from IncomeRecord r
        where r.personId in :personIds
          and r.effectiveFrom <= :asOf
          and (r.effectiveTo is null or r.effectiveTo >= :asOf)
        """)
    List<IncomeRecord> findEffectiveOn(
            @Param("personIds") Collection<UUID> personIds, @Param("asOf") LocalDate asOf);
}
