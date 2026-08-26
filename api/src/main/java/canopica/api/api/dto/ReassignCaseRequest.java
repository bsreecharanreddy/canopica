package canopica.api.api.dto;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record ReassignCaseRequest(@NotNull UUID workerId) {
}
