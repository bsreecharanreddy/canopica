package ies.rules;

import java.math.BigDecimal;
import java.util.UUID;

/**
 * Every SNAP figure the DMN model needs, already resolved for one household
 * size as of one decision date. Immutable; carries the version that produced
 * it so a determination can record exactly what it used (roadmap doc §3.5).
 */
public record SnapPolicyParameters(
        String parameterSetVersion,
        UUID parameterSetId,
        BigDecimal grossIncomeLimit,
        BigDecimal netIncomeLimit,
        BigDecimal standardDeduction,
        BigDecimal earnedIncomeDeductionRate,
        BigDecimal medicalExpenseThreshold,
        BigDecimal excessShelterCap,
        BigDecimal shelterIncomeShare,
        BigDecimal maxAllotment,
        BigDecimal minimumBenefit,
        int minimumBenefitMaxHouseholdSize,
        BigDecimal benefitReductionRate) {
}
