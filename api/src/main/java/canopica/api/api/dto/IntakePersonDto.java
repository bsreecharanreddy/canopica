package canopica.api.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import java.util.List;

/**
 * One household member as reported at intake, plus the income/expense records reported for them.
 * {@code usCitizen} and {@code purchasesAndPreparesFoodTogether} default to {@code true} (matching the
 * {@code person}/{@code household_member} schema defaults) when omitted.
 */
public record IntakePersonDto(
        @NotBlank String firstName,
        @NotBlank String lastName,
        @NotNull LocalDate dateOfBirth,
        @NotBlank String sex,
        Boolean usCitizen,
        @NotBlank String relationship,
        Boolean purchasesAndPreparesFoodTogether,
        // Voluntary civil-rights demographic data (7 CFR 272.6) -- both null when the applicant
        // declines to answer, same as a real form's own optional demographic section. See
        // Person.java's own comment; the DMN rules engine never reads either field.
        String race,
        Boolean hispanicOrigin,
        @Valid List<IntakeIncomeDto> incomes,
        @Valid List<IntakeExpenseDto> expenses) {

    public IntakePersonDto {
        incomes = incomes == null ? List.of() : incomes;
        expenses = expenses == null ? List.of() : expenses;
    }

    public boolean isUsCitizenOrDefault() {
        return usCitizen == null || usCitizen;
    }

    public boolean purchasesAndPreparesFoodTogetherOrDefault() {
        return purchasesAndPreparesFoodTogether == null || purchasesAndPreparesFoodTogether;
    }
}
