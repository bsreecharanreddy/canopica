package canopica.api.repo;

import canopica.api.domain.WorkActivity;
import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface WorkActivityRepository extends JpaRepository<WorkActivity, UUID> {

    @Query("""
        select w from WorkActivity w
        where w.personId in :personIds
          and w.effectiveFrom <= :asOf
          and (w.effectiveTo is null or w.effectiveTo >= :asOf)
        """)
    List<WorkActivity> findEffectiveOn(
            @Param("personIds") Collection<UUID> personIds, @Param("asOf") LocalDate asOf);
}
