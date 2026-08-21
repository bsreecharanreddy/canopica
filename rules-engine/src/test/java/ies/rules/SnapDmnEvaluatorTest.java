package ies.rules;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

/**
 * One test per SNAP eligibility scenario: gross/net income pass/fail, each
 * deduction applied correctly, and categorical eligibility -- the exact
 * coverage CLAUDE.md's testing policy requires for the rules engine. Every
 * expected value is hand-computed from the FY2025 arithmetic (see this
 * class's Javadoc-style comments below), not copied from the implementation.
 */
class SnapDmnEvaluatorTest {

    private final SnapDmnEvaluator evaluator = new SnapDmnEvaluator();

    static Stream<Arguments> scenarios() {
        return Stream.of(
            Arguments.of("single adult, no income, receives the full allotment",
                TestFixtures.facts().householdSize(1).build(),
                true, "292", "ELIGIBLE"),

            // gross 1500 <= 2798 -> PASS. Standard 204, earned 20% = 300 ->
            // adjusted 996. Shelter 1100 - (50% x 996 = 498) = 602 excess,
            // under the 712 cap -> net 996 - 602 = 394 <= 2152 -> PASS.
            // Benefit 768 - ceiling(394 x 0.30 = 118.2 -> 119) = 649.
            Arguments.of("three-person working household, capped shelter deduction",
                TestFixtures.facts().householdSize(3).earnedIncome("1500")
                        .shelterCost("800").utilityCost("300").build(),
                true, "649", "ELIGIBLE"),

            // Same as above but shelter 2000+300=2300: excess 2300-498=1802,
            // capped at 712 -> net 996-712=284 -> benefit 768-ceiling(85.2->86)=682.
            Arguments.of("high shelter cost is capped for a household with no elderly member",
                TestFixtures.facts().householdSize(3).earnedIncome("1500")
                        .shelterCost("2000").utilityCost("300").build(),
                true, "682", "ELIGIBLE"),

            // Same household with an elderly/disabled member: shelter excess is
            // uncapped -> net max(0, 996-1802)=0 -> benefit 768-0=768.
            Arguments.of("the same household with an elderly member gets an uncapped shelter deduction",
                TestFixtures.facts().householdSize(3).earnedIncome("1500")
                        .shelterCost("2000").utilityCost("300")
                        .hasElderlyOrDisabledMember(true).build(),
                true, "768", "ELIGIBLE"),

            Arguments.of("gross income over the limit is denied before any deduction runs",
                TestFixtures.facts().householdSize(1).unearnedIncome("2000").build(),
                false, "0", "GROSS_INCOME_EXCEEDS_LIMIT"),

            // Elderly/disabled -> exempt from the gross test, but net income
            // (2000-204=1796) still exceeds the 1255 net limit for size 1.
            Arguments.of("an elderly household is exempt from the gross test but still fails the net test",
                TestFixtures.facts().householdSize(1).unearnedIncome("2000")
                        .hasElderlyOrDisabledMember(true).build(),
                false, "0", "NET_INCOME_EXCEEDS_LIMIT"),

            // Categorical eligibility bypasses both income tests entirely.
            // adjusted = max(0, 2500-204)=2296; shelter excess 0; net 2296;
            // benefit computed = max(0, 536-ceiling(688.8))=max(0,536-689)=0
            // (negative clamped to 0) -> falls to the minimum-benefit row
            // since household size 2 <= minimumBenefitMaxHouseholdSize (2).
            Arguments.of("categorical eligibility bypasses both income tests",
                TestFixtures.facts().householdSize(2).unearnedIncome("2500")
                        .categoricallyEligible(true).build(),
                true, "23", "ELIGIBLE"),

            // unearned 1400, adjusted = max(0,1400-204)=1196, net=1196<=1255 PASS.
            // computed = max(0, 292-ceiling(358.8->359)) = max(0,-67)=0 -> minimum benefit.
            Arguments.of("a one-person household below the minimum receives the minimum benefit",
                TestFixtures.facts().householdSize(1).unearnedIncome("1400").build(),
                true, "23", "ELIGIBLE"),

            // Categorically eligible, size 3 (exceeds minimumBenefitMaxHouseholdSize
            // of 2), computed benefit clamps to 0 -> denied, not a $0 award.
            Arguments.of("a three-person household computing to zero is denied, not awarded zero",
                TestFixtures.facts().householdSize(3).unearnedIncome("3000")
                        .categoricallyEligible(true).build(),
                false, "0", "ZERO_BENEFIT_AMOUNT")
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void evaluatesSnapScenario(String name, SnapFacts facts,
                               boolean expectedEligible, String expectedBenefit,
                               String expectedReason) {
        SnapDecision decision = evaluator.evaluate(
                facts, TestFixtures.fy2025Parameters(facts.householdSize()));

        assertThat(decision.eligible()).isEqualTo(expectedEligible);
        assertThat(decision.benefitAmount()).isEqualByComparingTo(new BigDecimal(expectedBenefit));
        assertThat(decision.reasonCode()).isEqualTo(expectedReason);
    }

    /**
     * Required by CLAUDE.md's testing policy: "an old determination re-run
     * against its own parameter version still produces its original answer."
     * Proves the parameters are genuinely injected, not baked into the model
     * -- the same facts under two different parameter sets must diverge.
     */
    @Test
    void theSameFactsProduceDifferentBenefitsUnderDifferentParameterVersions() {
        SnapFacts facts = TestFixtures.facts().householdSize(3).earnedIncome("1500")
                .shelterCost("800").utilityCost("300").build();

        SnapDecision underFy2025 = evaluator.evaluate(facts, TestFixtures.fy2025Parameters(3));
        // A synthetic later version: max allotment 800, standard deduction 210.
        SnapDecision underLater = evaluator.evaluate(facts,
                TestFixtures.parameters(3).versionLabel("SNAP-TEST-LATER")
                        .maxAllotment("800").standardDeduction("210").build());

        assertThat(underFy2025.benefitAmount()).isEqualByComparingTo("649");
        // adjusted 1500-210-300=990; shelter excess 1100-495=605, capped at
        // 712 stays 605; net 990-605=385; benefit 800-ceiling(115.5->116)=684.
        assertThat(underLater.benefitAmount()).isEqualByComparingTo("684");
    }
}
