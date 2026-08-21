package canopica.portal.determination;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.portal.AbstractPostgresTest;
import canopica.portal.CaseFixtures;
import canopica.rules.SnapDecision;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * The exact property CLAUDE.md's testing policy names for the rules engine:
 * "an old determination re-run against its own parameter version still
 * produces its original answer." Reproduction pins to the stored
 * policy_parameter_set_id, not to "today" -- everything else in the
 * household's circumstances and the fiscal year in force is free to move.
 */
class DeterminationReproducibilityTest extends AbstractPostgresTest {

    @Autowired DeterminationService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void anOldDeterminationReRunAgainstItsOwnParameterVersionProducesItsOriginalAnswer() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID original = service.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        // Time moves on: a new fiscal year is in force and the household's
        // income has since changed. Neither may affect the stored decision.
        CaseFixtures.reportIncomeChange(jdbc, ids, "2600.00", LocalDate.of(2025, 11, 1));

        SnapDecision reproduced = service.reproduce(original);

        assertThat(reproduced.benefitAmount()).isEqualByComparingTo("649");
        assertThat(reproduced.reasonCode()).isEqualTo("ELIGIBLE");
        assertThat(reproduced.eligible()).isTrue();
    }

    @Test
    void aDeterminationMadeAfterOctoberFirstUsesTheNewFiscalYearsParameters() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        UUID later = service.determine(
                ids.programRequestId(), LocalDate.of(2025, 11, 15), LocalDate.of(2025, 11, 1), "SYSTEM");

        assertThat(jdbc.queryForObject(
                "select policy_parameter_version from eligibility_determination where id = ?",
                String.class, later)).isEqualTo("SNAP-FY2026");
    }
}
