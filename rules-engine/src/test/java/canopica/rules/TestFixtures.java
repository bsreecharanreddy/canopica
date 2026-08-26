package canopica.rules;

import java.math.BigDecimal;
import java.util.UUID;

/**
 * Test-only builders. The rules-engine module has no database, so these
 * hold the FY2025/FY2026 SNAP figures (see
 * docs/design/policy-parameter-provenance.md) as literals -- deliberately
 * not read from the same seed data the API's resolver reads, so a
 * scenario test cannot pass by coincidentally agreeing with a bug shared
 * between the seed and the fixture.
 */
final class TestFixtures {

    private TestFixtures() {
    }

    static FactsBuilder facts() {
        return new FactsBuilder();
    }

    /** FY2025 figures (household size 1-8) for the 48 states and DC. */
    static SnapPolicyParameters fy2025Parameters(int householdSize) {
        return parameters(householdSize).build();
    }

    static ParametersBuilder parameters(int householdSize) {
        BigDecimal[] maxAllotment = {null,
                bd(292), bd(536), bd(768), bd(975), bd(1158), bd(1390), bd(1536), bd(1756)};
        BigDecimal[] standardDeduction = {null,
                bd(204), bd(204), bd(204), bd(217), bd(254), bd(291), bd(291), bd(291)};
        BigDecimal[] grossIncomeLimit = {null,
                bd(1632), bd(2215), bd(2798), bd(3380), bd(3963), bd(4546), bd(5129), bd(5712)};
        BigDecimal[] netIncomeLimit = {null,
                bd(1255), bd(1704), bd(2152), bd(2600), bd(3049), bd(3497), bd(3945), bd(4394)};

        return new ParametersBuilder()
                .versionLabel("SNAP-FY2025")
                .parameterSetId(UUID.fromString("9f1c0e10-0000-4000-8000-000000000001"))
                .grossIncomeLimit(grossIncomeLimit[householdSize])
                .netIncomeLimit(netIncomeLimit[householdSize])
                .standardDeduction(standardDeduction[householdSize])
                .earnedIncomeDeductionRate(bd("0.20"))
                .medicalExpenseThreshold(bd(35))
                .excessShelterCap(bd(712))
                .shelterIncomeShare(bd("0.50"))
                .maxAllotment(maxAllotment[householdSize])
                .minimumBenefit(bd(23))
                .minimumBenefitMaxHouseholdSize(2)
                .benefitReductionRate(bd("0.30"));
    }

    private static BigDecimal bd(int value) {
        return BigDecimal.valueOf(value);
    }

    private static BigDecimal bd(String value) {
        return new BigDecimal(value);
    }

    static final class FactsBuilder {
        private int householdSize = 1;
        private BigDecimal earnedIncome = BigDecimal.ZERO;
        private BigDecimal unearnedIncome = BigDecimal.ZERO;
        private BigDecimal dependentCareCost = BigDecimal.ZERO;
        private BigDecimal medicalExpense = BigDecimal.ZERO;
        private BigDecimal shelterCost = BigDecimal.ZERO;
        private BigDecimal utilityCost = BigDecimal.ZERO;
        private boolean hasElderlyOrDisabledMember = false;
        private boolean categoricallyEligible = false;

        FactsBuilder householdSize(int value) {
            this.householdSize = value;
            return this;
        }

        FactsBuilder earnedIncome(String value) {
            this.earnedIncome = new BigDecimal(value);
            return this;
        }

        FactsBuilder unearnedIncome(String value) {
            this.unearnedIncome = new BigDecimal(value);
            return this;
        }

        FactsBuilder dependentCareCost(String value) {
            this.dependentCareCost = new BigDecimal(value);
            return this;
        }

        FactsBuilder medicalExpense(String value) {
            this.medicalExpense = new BigDecimal(value);
            return this;
        }

        FactsBuilder shelterCost(String value) {
            this.shelterCost = new BigDecimal(value);
            return this;
        }

        FactsBuilder utilityCost(String value) {
            this.utilityCost = new BigDecimal(value);
            return this;
        }

        FactsBuilder hasElderlyOrDisabledMember(boolean value) {
            this.hasElderlyOrDisabledMember = value;
            return this;
        }

        FactsBuilder categoricallyEligible(boolean value) {
            this.categoricallyEligible = value;
            return this;
        }

        SnapFacts build() {
            return new SnapFacts(householdSize, earnedIncome, unearnedIncome, dependentCareCost,
                    medicalExpense, shelterCost, utilityCost, hasElderlyOrDisabledMember,
                    categoricallyEligible);
        }
    }

    static final class ParametersBuilder {
        private String versionLabel;
        private UUID parameterSetId;
        private BigDecimal grossIncomeLimit;
        private BigDecimal netIncomeLimit;
        private BigDecimal standardDeduction;
        private BigDecimal earnedIncomeDeductionRate;
        private BigDecimal medicalExpenseThreshold;
        private BigDecimal excessShelterCap;
        private BigDecimal shelterIncomeShare;
        private BigDecimal maxAllotment;
        private BigDecimal minimumBenefit;
        private int minimumBenefitMaxHouseholdSize;
        private BigDecimal benefitReductionRate;

        ParametersBuilder versionLabel(String value) {
            this.versionLabel = value;
            return this;
        }

        ParametersBuilder parameterSetId(UUID value) {
            this.parameterSetId = value;
            return this;
        }

        ParametersBuilder grossIncomeLimit(BigDecimal value) {
            this.grossIncomeLimit = value;
            return this;
        }

        ParametersBuilder netIncomeLimit(BigDecimal value) {
            this.netIncomeLimit = value;
            return this;
        }

        ParametersBuilder standardDeduction(BigDecimal value) {
            this.standardDeduction = value;
            return this;
        }

        ParametersBuilder earnedIncomeDeductionRate(BigDecimal value) {
            this.earnedIncomeDeductionRate = value;
            return this;
        }

        ParametersBuilder medicalExpenseThreshold(BigDecimal value) {
            this.medicalExpenseThreshold = value;
            return this;
        }

        ParametersBuilder excessShelterCap(BigDecimal value) {
            this.excessShelterCap = value;
            return this;
        }

        ParametersBuilder shelterIncomeShare(BigDecimal value) {
            this.shelterIncomeShare = value;
            return this;
        }

        ParametersBuilder maxAllotment(BigDecimal value) {
            this.maxAllotment = value;
            return this;
        }

        ParametersBuilder maxAllotment(String value) {
            this.maxAllotment = new BigDecimal(value);
            return this;
        }

        ParametersBuilder minimumBenefit(BigDecimal value) {
            this.minimumBenefit = value;
            return this;
        }

        ParametersBuilder minimumBenefitMaxHouseholdSize(int value) {
            this.minimumBenefitMaxHouseholdSize = value;
            return this;
        }

        ParametersBuilder benefitReductionRate(BigDecimal value) {
            this.benefitReductionRate = value;
            return this;
        }

        ParametersBuilder standardDeduction(String value) {
            this.standardDeduction = new BigDecimal(value);
            return this;
        }

        SnapPolicyParameters build() {
            return new SnapPolicyParameters(versionLabel, parameterSetId, grossIncomeLimit,
                    netIncomeLimit, standardDeduction, earnedIncomeDeductionRate,
                    medicalExpenseThreshold, excessShelterCap, shelterIncomeShare, maxAllotment,
                    minimumBenefit, minimumBenefitMaxHouseholdSize, benefitReductionRate);
        }
    }
}
