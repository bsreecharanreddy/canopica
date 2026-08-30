package canopica.api.api;

import canopica.api.api.dto.QcSampleRunResponse;
import canopica.api.qc.PaymentErrorReview;
import canopica.api.qc.QcSamplingService;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * The QC / Payment Error Rate Assistant's internal sample-trigger endpoint (Phase 4 Task 4). {@code
 * SecurityConfig} restricts all of {@code /api/internal/qc/**} to the ADMIN role -- an internal,
 * schedule-triggered operation (Airflow, via a real service-account client), not a supervisor-facing one,
 * same "narrowest existing role that fits" posture {@link PolicyParameterProposalController}'s own doc
 * comment takes for a different internal-operation endpoint. Task 5 adds the human review-queue endpoints
 * here as a separate, {@code SUPERVISOR}-scoped surface.
 */
@RestController
class QcController {

    private final QcSamplingService qcSamplingService;

    QcController(QcSamplingService qcSamplingService) {
        this.qcSamplingService = qcSamplingService;
    }

    @PostMapping("/api/internal/qc/run-sample")
    QcSampleRunResponse runSample(@RequestParam(required = false) Integer sampleSize) {
        int size = sampleSize != null ? sampleSize : qcSamplingService.computeDefaultSampleSize();
        List<PaymentErrorReview> reviews = qcSamplingService.runSample(size);
        long flagged = reviews.stream().filter(review -> review.getErrorAmount().compareTo(BigDecimal.ZERO) != 0).count();
        return new QcSampleRunResponse(reviews.size(), (int) flagged);
    }
}
