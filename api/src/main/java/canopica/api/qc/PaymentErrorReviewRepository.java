package canopica.api.qc;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentErrorReviewRepository extends JpaRepository<PaymentErrorReview, UUID> {

    Optional<PaymentErrorReview> findByDeterminationId(UUID determinationId);

    /** Task 5's review queue: unreviewed discrepancies, largest error first
     * ({@code payment_error_review_review_queue_idx}, V26) -- a zero-diff sampled case is real evidence for
     * the mart but never needs a reviewer's attention. */
    List<PaymentErrorReview> findByReviewOutcomeIsNullAndErrorAmountNotOrderByErrorAmountDesc(BigDecimal errorAmount);
}
