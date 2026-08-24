package canopica.portal.policy;

import com.fasterxml.jackson.annotation.JsonFormat;
import canopica.portal.domain.PolicyParameter;
import java.math.BigDecimal;

/**
 * One figure of the parameter set being diffed against, sent *to* the AI service.
 *
 * <p>The AI service has no database access of its own, by design (Phase 2 design doc §2.3) -- so the portal,
 * which owns the data, tells it what is currently in force rather than letting it go and look. That is also
 * what makes the copilot's scope enforceable: it can only propose changes to figures that appear in this
 * list, and anything else it names is refused on both sides of the wire.
 */
public record CurrentParameterValue(
        String name,
        Integer householdSize,
        @JsonFormat(shape = JsonFormat.Shape.STRING) BigDecimal value,
        String unit) {

    public static CurrentParameterValue from(PolicyParameter parameter) {
        return new CurrentParameterValue(
                parameter.getName(), parameter.getHouseholdSize(), parameter.getNumericValue(), parameter.getUnit());
    }
}
