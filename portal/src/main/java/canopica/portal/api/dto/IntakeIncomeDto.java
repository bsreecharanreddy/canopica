package canopica.portal.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.math.BigDecimal;
import java.time.LocalDate;

@EffectiveRange
public record IntakeIncomeDto(
        @NotBlank String incomeType,
        boolean earned,
        @NotNull @PositiveOrZero BigDecimal monthlyAmount,
        @NotNull LocalDate effectiveFrom,
        LocalDate effectiveTo) implements EffectiveDated {
}
