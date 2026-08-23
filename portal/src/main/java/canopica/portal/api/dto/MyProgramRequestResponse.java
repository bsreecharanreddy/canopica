package canopica.portal.api.dto;

import java.time.Instant;
import java.util.UUID;

public record MyProgramRequestResponse(UUID programRequestId, String programCode, String status, Instant submittedAt) {
}
