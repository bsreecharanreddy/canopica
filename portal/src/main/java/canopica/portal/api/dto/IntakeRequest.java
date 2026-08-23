package canopica.portal.api.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

/**
 * A customer's SNAP application submission. {@code channel} defaults to {@code ONLINE} (this is the only
 * channel this HTTP API represents) and {@code paysUtilitiesSeparately} defaults to {@code false} when
 * omitted, matching the {@code application}/{@code living_arrangement} schema defaults. {@code resources}
 * is household-level (unlike {@code incomes}/{@code expenses}, which are per member) and defaults to
 * empty -- most households reporting no liquid resources is a legitimate, common case, not an omission.
 */
public record IntakeRequest(
        @NotBlank String county,
        @NotBlank String addressLine1,
        String addressLine2,
        @NotBlank String city,
        @NotBlank String state,
        @NotBlank String zipCode,
        String channel,
        @NotBlank String arrangementType,
        Boolean paysUtilitiesSeparately,
        @NotEmpty @Valid List<IntakePersonDto> members,
        @Valid List<IntakeResourceDto> resources) {

    public IntakeRequest {
        resources = resources == null ? List.of() : resources;
    }

    public String channelOrDefault() {
        return channel == null || channel.isBlank() ? "ONLINE" : channel;
    }

    public boolean paysUtilitiesSeparatelyOrDefault() {
        return Boolean.TRUE.equals(paysUtilitiesSeparately);
    }
}
