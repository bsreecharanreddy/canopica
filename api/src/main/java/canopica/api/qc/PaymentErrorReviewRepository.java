package canopica.api.qc;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentErrorReviewRepository extends JpaRepository<PaymentErrorReview, UUID> {

    Optional<PaymentErrorReview> findByDeterminationId(UUID determinationId);
}
