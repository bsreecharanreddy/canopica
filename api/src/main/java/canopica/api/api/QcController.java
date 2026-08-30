package canopica.api.api;

import canopica.api.api.dto.PaymentErrorReviewResponse;
import canopica.api.api.dto.QcSampleRunResponse;
import canopica.api.qc.PaymentErrorReview;
import canopica.api.qc.PaymentErrorReviewRepository;
import canopica.api.qc.QcReviewService;
import canopica.api.qc.QcSamplingService;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * The QC / Payment Error Rate Assistant's two surfaces: an internal sample-trigger endpoint (Phase 4 Task 4)
 * and the human review queue (Task 5). {@code SecurityConfig} restricts {@code /api/internal/qc/**} to the
 * ADMIN role -- an internal, schedule-triggered operation (Airflow, via a real service-account client), not a
 * supervisor-facing one, same "narrowest existing role that fits" posture {@link
 * PolicyParameterProposalController}'s own doc comment takes for a different internal-operation endpoint --
 * and {@code /api/qc/**} to SUPERVISOR, same role and reasoning {@link FraudReviewController}'s own doc
 * comment gives for {@code /api/fraud/**}. Neither {@code confirm} nor {@code dismiss} ever touches the
 * original determination or its benefit amount (constraint 19) -- QC flags an estimate of error, it does not
 * fix one.
 */
@RestController
class QcController {

    private final QcSamplingService qcSamplingService;
    private final PaymentErrorReviewRepository reviews;
    private final QcReviewService qcReviewService;

    QcController(
            QcSamplingService qcSamplingService, PaymentErrorReviewRepository reviews, QcReviewService qcReviewService) {
        this.qcSamplingService = qcSamplingService;
        this.reviews = reviews;
        this.qcReviewService = qcReviewService;
    }

    @PostMapping("/api/internal/qc/run-sample")
    QcSampleRunResponse runSample(@RequestParam(required = false) Integer sampleSize) {
        int size = sampleSize != null ? sampleSize : qcSamplingService.computeDefaultSampleSize();
        List<PaymentErrorReview> sampled = qcSamplingService.runSample(size);
        long flagged = sampled.stream().filter(review -> review.getErrorAmount().compareTo(BigDecimal.ZERO) != 0).count();
        return new QcSampleRunResponse(sampled.size(), (int) flagged);
    }

    @GetMapping("/api/qc/review-queue")
    List<PaymentErrorReviewResponse> reviewQueue() {
        return reviews.findByReviewOutcomeIsNullAndErrorAmountNotOrderByErrorAmountDesc(BigDecimal.ZERO).stream()
                .map(PaymentErrorReviewResponse::from)
                .toList();
    }

    @PostMapping("/api/qc/{reviewId}/confirm")
    PaymentErrorReviewResponse confirm(@PathVariable UUID reviewId, Authentication authentication) {
        return PaymentErrorReviewResponse.from(qcReviewService.confirmError(reviewId, authentication.getName()));
    }

    @PostMapping("/api/qc/{reviewId}/dismiss")
    PaymentErrorReviewResponse dismiss(@PathVariable UUID reviewId, Authentication authentication) {
        return PaymentErrorReviewResponse.from(qcReviewService.dismiss(reviewId, authentication.getName()));
    }
}
