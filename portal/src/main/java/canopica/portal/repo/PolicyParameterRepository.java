package canopica.portal.repo;

import canopica.portal.domain.PolicyParameter;
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
}
