package canopica.portal.api.dto;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/** {@code determinations} is newest-first: append-only history, never an overwrite. */
public record CaseDetailResponse(
        UUID programRequestId, UUID applicationId, UUID householdId, String householdHeadName,
        String programCode, String status, LocalDate requestedOn,
        List<DeterminationResponse> determinations) {
}
