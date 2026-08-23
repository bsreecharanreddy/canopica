package ies.portal.intake;

import java.math.BigDecimal;

/**
 * 7 CFR 273.2(i)(1): expedited (7-day) processing applies when a household's
 * gross monthly income is under $150 and liquid resources are $100 or less,
 * or when combined gross monthly income and liquid resources are less than
 * the household's monthly rent-or-mortgage-and-utility expenses. Intake-time
 * only -- this decides which SNAP processing-time standard (30 days normal,
 * 7 days expedited) applies to the request, it does not touch the DMN model
 * or the benefit calculation itself (design doc §2.6).
 */
final class ExpeditedEligibility {

    private static final BigDecimal GROSS_INCOME_THRESHOLD = new BigDecimal("150");
    private static final BigDecimal LIQUID_RESOURCES_THRESHOLD = new BigDecimal("100");

    private ExpeditedEligibility() {
    }

    static boolean isExpedited(BigDecimal grossMonthlyIncome, BigDecimal liquidResources, BigDecimal shelterCost) {
        boolean lowIncomeAndResources = grossMonthlyIncome.compareTo(GROSS_INCOME_THRESHOLD) < 0
                && liquidResources.compareTo(LIQUID_RESOURCES_THRESHOLD) <= 0;
        boolean combinedBelowShelterCost = grossMonthlyIncome.add(liquidResources).compareTo(shelterCost) < 0;
        return lowIncomeAndResources || combinedBelowShelterCost;
    }
}
