package canopica.portal.api.dto;

import java.util.UUID;

public record IntakeResponse(UUID applicationId, UUID programRequestId) {
}
