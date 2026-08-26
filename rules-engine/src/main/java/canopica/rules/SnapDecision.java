package canopica.rules;

import java.math.BigDecimal;
import java.util.Map;

/**
 * @param trace every named DMN decision's result, in evaluation order.
 *              Persisted verbatim as DETERMINATION_TRACE (api Task 5).
 */
public record SnapDecision(
        boolean eligible,
        BigDecimal benefitAmount,
        String reasonCode,
        Map<String, Object> trace) {
}
