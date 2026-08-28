package canopica.api.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * The worker's final, edited-or-accepted field values (Task 4, design doc §2.3's mandatory confirmation
 * gate) -- this request, not the extraction itself, is what actually reaches a case record.
 * {@code satisfiedVerificationIds} lets the worker accept or drop any of the extraction's own {@code
 * matched_verification_ids} guesses; {@code incomeRecords} is empty for document types with nothing to
 * post to {@code income_record} (e.g. a verification-checklist document that only satisfies a verification).
 */
public record ConfirmDocumentRequest(
        List<UUID> satisfiedVerificationIds, @Valid List<ConfirmedIncomeEntry> incomeRecords) {

    public ConfirmDocumentRequest {
        satisfiedVerificationIds = satisfiedVerificationIds == null ? List.of() : satisfiedVerificationIds;
        incomeRecords = incomeRecords == null ? List.of() : incomeRecords;
    }

    /** Same fields {@link IntakeIncomeDto} validates, plus the {@code personId} intake already knows from context. */
    @EffectiveRange
    public record ConfirmedIncomeEntry(
            @NotNull UUID personId,
            @NotBlank String incomeType,
            boolean earned,
            @NotNull @PositiveOrZero BigDecimal monthlyAmount,
            @NotNull LocalDate effectiveFrom,
            LocalDate effectiveTo) implements EffectiveDated {
    }
}
