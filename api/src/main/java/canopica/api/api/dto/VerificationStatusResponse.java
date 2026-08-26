package canopica.api.api.dto;

import canopica.api.domain.Verification;
import canopica.api.domain.VerificationResponse;
import java.time.LocalDate;
import java.util.UUID;

/**
 * {@code outcome} is null until {@code status} moves to {@code RECEIVED}. Deliberately has no field for
 * the mock response's raw payload -- an FTI-style safeguard (design doc §2.2): the raw value cannot leak
 * through this shape because it was never given one.
 */
public record VerificationStatusResponse(
        UUID verificationId, String dataElement, String status, LocalDate dueOn, LocalDate satisfiedOn, String outcome) {

    public static VerificationStatusResponse from(Verification verification, VerificationResponse response) {
        return new VerificationStatusResponse(
                verification.getId(), verification.getDataElement(), verification.getStatus(),
                verification.getDueOn(), verification.getSatisfiedOn(),
                response == null ? null : response.getOutcome());
    }
}
