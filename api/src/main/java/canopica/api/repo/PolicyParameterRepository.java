package canopica.api.repo;

import canopica.api.domain.PolicyParameter;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PolicyParameterRepository extends JpaRepository<PolicyParameter, UUID> {

    @Query("""
        select p from PolicyParameter p
        where p.parameterSetId = :setId
          and (p.householdSize is null or p.householdSize = :size)
        """)
    List<PolicyParameter> findForSet(
            @Param("setId") UUID parameterSetId, @Param("size") int householdSize);

    /**
     * Every figure in a set, unfiltered by household size -- what {@code PolicyParameterPublishService} needs
     * to copy a set forward, and what the rule-authoring copilot is shown as "what is currently in force".
     * {@link #findForSet} deliberately narrows to one size because a determination only ever concerns one
     * household; these two callers concern the whole set.
     */
    List<PolicyParameter> findByParameterSetIdOrderByNameAscHouseholdSizeAsc(UUID parameterSetId);
}
