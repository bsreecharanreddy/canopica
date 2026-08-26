package canopica.api.api.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record CaseSummaryResponse(
        UUID programRequestId, String householdHeadName, String status, Instant submittedAt,
        LatestDetermination latestDetermination) {

    /** Null when no determination has been made yet. */
    public record LatestDetermination(boolean eligible, BigDecimal benefitAmount, Instant decidedAt) {
    }
}
