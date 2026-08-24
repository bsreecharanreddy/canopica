package canopica.portal.repo;

import canopica.portal.domain.PolicyParameterProposal;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PolicyParameterProposalRepository extends JpaRepository<PolicyParameterProposal, UUID> {

    /** The reviewer's own screen: what is waiting on me, newest first. Backed by V14's own index. */
    List<PolicyParameterProposal> findByStatusOrderByCreatedAtDesc(String status);
}
