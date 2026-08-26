package canopica.api.repo;

import canopica.api.domain.ExpenseRecord;
import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ExpenseRecordRepository extends JpaRepository<ExpenseRecord, UUID> {

    @Query("""
        select r from ExpenseRecord r
        where r.personId in :personIds
          and r.effectiveFrom <= :asOf
          and (r.effectiveTo is null or r.effectiveTo >= :asOf)
        """)
    List<ExpenseRecord> findEffectiveOn(
            @Param("personIds") Collection<UUID> personIds, @Param("asOf") LocalDate asOf);
}
