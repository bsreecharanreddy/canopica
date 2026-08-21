package ies.portal.determination;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ies.portal.AbstractPostgresTest;
import ies.portal.CaseFixtures;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class DeterminationServiceTest extends AbstractPostgresTest {

    @Autowired DeterminationService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void persistsADeterminationAndItsCompleteTrace() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        UUID determinationId = service.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        var row = jdbc.queryForMap(
                "select * from eligibility_determination where id = ?", determinationId);
        assertThat(row.get("eligible")).isEqualTo(true);
        assertThat((BigDecimal) row.get("benefit_amount")).isEqualByComparingTo("649");
        assertThat(row.get("reason_code")).isEqualTo("ELIGIBLE");
        assertThat(row.get("policy_parameter_version")).isEqualTo("SNAP-FY2025");
        assertThat(row.get("decided_by")).isEqualTo("SYSTEM");

        var trace = jdbc.queryForMap(
                "select * from determination_trace where determination_id = ?", determinationId);
        assertThat(trace.get("dmn_model_hash")).asString().hasSize(64);
        assertThat(trace.get("dmn_model_name")).isEqualTo("snap-eligibility");
        assertThat(trace.get("decision_results").toString())
                .contains("Excess Shelter Deduction", "Net Income", "Benefit Amount");
        assertThat(trace.get("input_snapshot").toString()).contains("householdSize");
    }

    @Test
    void refusesToMutateAnExistingDetermination() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID id = service.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        assertThatThrownBy(() -> jdbc.update(
                "update eligibility_determination set benefit_amount = 1 where id = ?", id))
                .hasMessageContaining("append-only");
    }

    @Test
    void aDenialStoresAZeroBenefitAmountAndTheDenialReasonCode() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        // Push gross income over the FY2025 3-person limit (2798).
        CaseFixtures.reportIncomeChange(jdbc, ids, "5000.00", LocalDate.of(2025, 1, 1));

        UUID determinationId = service.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        var row = jdbc.queryForMap(
                "select * from eligibility_determination where id = ?", determinationId);
        assertThat(row.get("eligible")).isEqualTo(false);
        assertThat((BigDecimal) row.get("benefit_amount")).isEqualByComparingTo("0");
        assertThat(row.get("reason_code")).isEqualTo("GROSS_INCOME_EXCEEDS_LIMIT");
    }
}
