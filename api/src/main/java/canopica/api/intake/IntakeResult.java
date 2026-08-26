package canopica.api.intake;

import java.util.UUID;

public record IntakeResult(UUID applicationId, UUID programRequestId) {
}
