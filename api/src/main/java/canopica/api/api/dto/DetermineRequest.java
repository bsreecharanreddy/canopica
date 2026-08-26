package canopica.api.api.dto;

import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record DetermineRequest(@NotNull LocalDate asOfDate, @NotNull LocalDate benefitMonth) {
}
