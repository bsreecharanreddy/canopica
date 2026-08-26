package canopica.api.api.dto;

import canopica.api.policy.PolicyParameterPublishService.PublicationDetails;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

/**
 * A human's decision on one proposal.
 *
 * <p>The three publication fields are required on accept and meaningless on reject, so they are nullable
 * here and required conditionally. None of them can be derived: an effective date is a policy fact the memo
 * states, the citation is the memo, and {@code versionLabel} is unique by database constraint. Defaulting
 * any of them would publish a parameter version under a date or a label nobody chose.
 */
public record ReviewProposalRequest(
        @NotNull Boolean accept,
        String versionLabel,
        LocalDate effectiveFrom,
        String sourceCitation) {

    /**
     * A conditional constraint expressed through Bean Validation rather than as a runtime check, so it comes
     * back as a 400 with a message alongside any other field errors -- the same shape every other invalid
     * request in this API produces -- instead of an exception the handler would have to classify.
     */
    @AssertTrue(message = "accepting a proposal requires versionLabel, effectiveFrom and sourceCitation")
    public boolean isPublicationDetailsSuppliedWhenAccepting() {
        return !Boolean.TRUE.equals(accept) || hasPublicationDetails();
    }

    public PublicationDetails publicationDetails() {
        if (!hasPublicationDetails()) {
            // Unreachable through the API (the constraint above rejects it first); kept so a future
            // non-HTTP caller cannot publish a set with a missing label or date.
            throw new IllegalArgumentException(
                    "accepting a proposal requires versionLabel, effectiveFrom and sourceCitation");
        }
        return new PublicationDetails(versionLabel, effectiveFrom, sourceCitation);
    }

    private boolean hasPublicationDetails() {
        return versionLabel != null && !versionLabel.isBlank()
                && effectiveFrom != null
                && sourceCitation != null && !sourceCitation.isBlank();
    }
}
