package canopica.api.policy;

import java.math.BigDecimal;

/**
 * One line of a rule-authoring diff: what a figure is now, what the copilot proposes it become, and why.
 *
 * <p>Deliberately one type doing three jobs -- it binds the AI service's HTTP response, it is what gets
 * stored in {@code policy_parameter_proposal.proposed_values}, and it is what the reviewer's screen renders.
 * Three near-identical records would drift, and the drift would show up as a figure that means one thing in
 * the database and another on the screen.
 *
 * <p>{@code oldValue} and {@code unit} are authored by {@code PolicyParameterPublishService} from the current
 * parameter set, never taken from the model -- the AI service applies the same rule on its own side, and
 * neither side trusts the other to have done it.
 */
public record ProposedParameterValue(
        String name,
        // Null means the parameter is scalar (a rate or a threshold), matching V3's own null-household_size
        // convention. Boxed rather than int for exactly that reason.
        Integer householdSize,
        // Money and rates cross this wire as JSON strings in both directions: the AI service emits them as
        // strings (canopica_ai...rule_authoring.schema.DecimalValue), and JacksonConfig makes every BigDecimal
        // leave this service the same way, so a figure never passes through a float in either direction.
        BigDecimal oldValue,
        BigDecimal newValue,
        String unit,
        String rationale) {}
