package ies.portal.api.dto;

import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record DetermineRequest(@NotNull LocalDate asOfDate, @NotNull LocalDate benefitMonth) {
}
