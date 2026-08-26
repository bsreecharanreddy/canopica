package canopica.api.intake;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

/**
 * Table-driven, matching rules-engine's SnapDmnEvaluatorTest style -- 7 CFR
 * 273.2(i)(1)'s two independent legs (income-and-resources, and
 * combined-below-shelter-cost) each proven separately, plus the boundary
 * values the regulation states literally ("under $150", "$100 or less").
 */
class ExpeditedEligibilityTest {

    static Stream<Arguments> scenarios() {
        return Stream.of(
            Arguments.of("under both the income and resource thresholds is expedited",
                "100", "50", "9999", true),

            Arguments.of("over the income threshold only is not expedited",
                "200", "50", "100", false),

            Arguments.of("over the resource threshold only is not expedited",
                "100", "150", "100", false),

            Arguments.of("both flat thresholds exceeded, but combined income+resources still under shelter cost",
                "200", "150", "500", true),

            Arguments.of("gross income exactly at the $150 threshold does not qualify (strictly under)",
                "150", "100", "0", false),

            Arguments.of("liquid resources exactly at the $100 threshold still qualifies (inclusive)",
                "100", "100", "0", true),

            Arguments.of("combined income plus resources exactly equal to shelter cost does not qualify (strictly under)",
                "300", "200", "500", false)
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void evaluatesExpeditedEligibility(String name, String grossMonthlyIncome, String liquidResources,
                                        String shelterCost, boolean expectedExpedited) {
        boolean expedited = ExpeditedEligibility.isExpedited(
                new BigDecimal(grossMonthlyIncome), new BigDecimal(liquidResources), new BigDecimal(shelterCost));

        assertThat(expedited).isEqualTo(expectedExpedited);
    }
}
