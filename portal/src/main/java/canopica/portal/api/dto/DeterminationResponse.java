package canopica.portal.api.dto;

import canopica.portal.domain.EligibilityDetermination;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public record DeterminationResponse(
        UUID determinationId, boolean eligible, BigDecimal benefitAmount,
        String reasonCode, String policyParameterVersion,
        LocalDate benefitMonth, LocalDate asOfDate, Instant decidedAt) {

    public static DeterminationResponse from(EligibilityDetermination d) {
        return new DeterminationResponse(
                d.getId(), d.isEligible(), d.getBenefitAmount(), d.getReasonCode(),
                d.getPolicyParameterVersion(), d.getBenefitMonth(), d.getAsOfDate(), d.getDecidedAt());
    }
}
