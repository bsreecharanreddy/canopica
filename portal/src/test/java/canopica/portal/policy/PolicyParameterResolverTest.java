package canopica.portal.policy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.portal.AbstractPostgresTest;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class PolicyParameterResolverTest extends AbstractPostgresTest {

    @Autowired PolicyParameterResolver resolver;

    @Test
    void resolvesTheFiscalYearInForceOnTheDecisionDate() {
        var june2025 = resolver.resolveSnap(LocalDate.of(2025, 6, 15), 3);
        assertThat(june2025.parameterSetVersion()).isEqualTo("SNAP-FY2025");
        assertThat(june2025.maxAllotment()).isEqualByComparingTo("768");
        assertThat(june2025.standardDeduction()).isEqualByComparingTo("204");
    }

    @Test
    void resolvesTheNextFiscalYearOnAndAfterOctoberFirst() {
        var oct2025 = resolver.resolveSnap(LocalDate.of(2025, 10, 1), 3);
        assertThat(oct2025.parameterSetVersion()).isEqualTo("SNAP-FY2026");
        assertThat(oct2025.maxAllotment()).isEqualByComparingTo("785");
    }

    @Test
    void theBoundaryIsExactAndNotOffByOneDay() {
        assertThat(resolver.resolveSnap(LocalDate.of(2025, 9, 30), 3).parameterSetVersion())
                .isEqualTo("SNAP-FY2025");
    }

    @Test
    void sizeScopedParametersDifferBySizeWhileScalarsDoNot() {
        var one = resolver.resolveSnap(LocalDate.of(2025, 6, 15), 1);
        var six = resolver.resolveSnap(LocalDate.of(2025, 6, 15), 6);
        assertThat(one.standardDeduction()).isEqualByComparingTo("204");
        assertThat(six.standardDeduction()).isEqualByComparingTo("291");
        assertThat(one.earnedIncomeDeductionRate())
                .isEqualByComparingTo(six.earnedIncomeDeductionRate());
    }

    @Test
    void rejectsAHouseholdSizeTheParameterSetDoesNotCover() {
        assertThatThrownBy(() -> resolver.resolveSnap(LocalDate.of(2025, 6, 15), 9))
                .isInstanceOf(PolicyParameterNotFoundException.class)
                .hasMessageContaining("household size 9");
    }

    @Test
    void rejectsADateNoPublishedSetCovers() {
        assertThatThrownBy(() -> resolver.resolveSnap(LocalDate.of(2019, 1, 1), 3))
                .isInstanceOf(PolicyParameterNotFoundException.class);
    }
}
