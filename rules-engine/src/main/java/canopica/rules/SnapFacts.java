package canopica.rules;

import java.math.BigDecimal;

/**
 * One household's circumstances as of one decision date, already resolved
 * from effective-dated records by the caller. All amounts are monthly.
 */
public record SnapFacts(
        int householdSize,
        BigDecimal earnedIncome,
        BigDecimal unearnedIncome,
        BigDecimal dependentCareCost,
        BigDecimal medicalExpense,
        BigDecimal shelterCost,
        BigDecimal utilityCost,
        boolean hasElderlyOrDisabledMember,
        boolean categoricallyEligible) {
}
