package canopica.api.api.dto;

import com.fasterxml.jackson.annotation.JsonRawValue;
import canopica.api.domain.PolicyParameterProposal;
import java.time.Instant;
import java.util.UUID;

/**
 * One proposal as the review screen sees it: the diff, who is accountable at each step, and which model
 * drafted it under which prompt.
 */
public record ParameterProposalResponse(
        UUID id,
        UUID currentParameterSetId,
        String currentVersionLabel,
        String sourceExcerpt,
        // Emitted verbatim from the jsonb column rather than parsed into a List and re-serialised. Cheaper,
        // and it means the reviewer's screen renders exactly the bytes that were stored -- a Jackson round
        // trip through BigDecimal would be free to render "298.0" where "298" was recorded.
        @JsonRawValue String proposedValues,
        String status,
        String proposedBy,
        String reviewedBy,
        Instant reviewedAt,
        UUID publishedParameterSetId,
        String generationModel,
        String promptVersion,
        Instant createdAt) {

    public static ParameterProposalResponse from(PolicyParameterProposal proposal, String currentVersionLabel) {
        return new ParameterProposalResponse(
                proposal.getId(),
                proposal.getCurrentParameterSetId(),
                currentVersionLabel,
                proposal.getSourceExcerpt(),
                proposal.getProposedValues(),
                proposal.getStatus().name(),
                proposal.getProposedBy(),
                proposal.getReviewedBy(),
                proposal.getReviewedAt(),
                proposal.getPublishedParameterSetId(),
                proposal.getGenerationModel(),
                proposal.getPromptVersion(),
                proposal.getCreatedAt());
    }
}
