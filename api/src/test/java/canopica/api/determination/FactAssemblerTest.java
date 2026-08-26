package canopica.api.determination;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import canopica.rules.SnapFacts;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class FactAssemblerTest extends AbstractPostgresTest {

    @Autowired FactAssembler assembler;
    @Autowired JdbcTemplate jdbc;

    @Test
    void assemblesFactsAsOfADateAndExcludesLaterEffectiveRecords() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        // A raise effective 2025-07-01 must not appear in a June assembly.
        CaseFixtures.reportIncomeChange(jdbc, ids, "2100.00", LocalDate.of(2025, 7, 1));

        SnapFacts facts = assembler.assemble(ids.householdId(), LocalDate.of(2025, 6, 15));

        assertThat(facts.householdSize()).isEqualTo(3);
        assertThat(facts.earnedIncome()).isEqualByComparingTo("1500.00");
        assertThat(facts.shelterCost()).isEqualByComparingTo("800.00");
        assertThat(facts.utilityCost()).isEqualByComparingTo("300.00");
        assertThat(facts.hasElderlyOrDisabledMember()).isFalse();
        assertThat(facts.categoricallyEligible()).isFalse();
    }

    @Test
    void assemblesTheLaterIncomeWhenAssembledAfterItsEffectiveDate() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        CaseFixtures.reportIncomeChange(jdbc, ids, "2100.00", LocalDate.of(2025, 7, 1));

        SnapFacts facts = assembler.assemble(ids.householdId(), LocalDate.of(2025, 7, 15));

        // Both the original and the new record are effective on 2025-07-15
        // (the original has no effective_to), so both sum into earned income.
        assertThat(facts.earnedIncome()).isEqualByComparingTo("3600.00");
    }

    @Test
    void aMemberAgedSixtyOrOlderMarksTheHouseholdAsHavingAnElderlyMember() {
        UUID elderlyId = UUID.randomUUID();
        jdbc.update(
                "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
                        + "values (?, 'Elder', 'Test', date '1960-01-01', ?, 'X')",
                elderlyId, "tok-" + elderlyId);
        UUID householdId = UUID.randomUUID();
        jdbc.update(
                "insert into household (id, head_person_id, county, address_line1, city, state, zip_code) "
                        + "values (?, ?, 'Test County', '1 St', 'Testville', 'TS', '00000')",
                householdId, elderlyId);
        jdbc.update(
                "insert into household_member (id, household_id, person_id, relationship, effective_from) "
                        + "values (?, ?, ?, 'SELF', date '2025-01-01')",
                UUID.randomUUID(), householdId, elderlyId);

        SnapFacts facts = assembler.assemble(householdId, LocalDate.of(2025, 6, 15));

        assertThat(facts.hasElderlyOrDisabledMember()).isTrue();
    }

    @Test
    void anEffectiveDisabilityRecordMarksTheHouseholdAsHavingADisabledMember() {
        UUID memberId = UUID.randomUUID();
        jdbc.update(
                "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
                        + "values (?, 'Younger', 'Test', date '1995-01-01', ?, 'X')",
                memberId, "tok-" + memberId);
        UUID householdId = UUID.randomUUID();
        jdbc.update(
                "insert into household (id, head_person_id, county, address_line1, city, state, zip_code) "
                        + "values (?, ?, 'Test County', '1 St', 'Testville', 'TS', '00000')",
                householdId, memberId);
        jdbc.update(
                "insert into household_member (id, household_id, person_id, relationship, effective_from) "
                        + "values (?, ?, ?, 'SELF', date '2025-01-01')",
                UUID.randomUUID(), householdId, memberId);
        jdbc.update(
                "insert into disability_record (id, person_id, basis, effective_from) "
                        + "values (?, ?, 'SSDI', date '2025-01-01')",
                UUID.randomUUID(), memberId);

        SnapFacts facts = assembler.assemble(householdId, LocalDate.of(2025, 6, 15));

        assertThat(facts.hasElderlyOrDisabledMember()).isTrue();
    }

    @Test
    void anSsiIncomeRecordMakesTheHouseholdCategoricallyEligible() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, monthly_amount, effective_from) "
                        + "values (?, ?, 'SSI', false, 200.00, date '2025-01-01')",
                UUID.randomUUID(), ids.headPersonId());

        SnapFacts facts = assembler.assemble(ids.householdId(), LocalDate.of(2025, 6, 15));

        assertThat(facts.categoricallyEligible()).isTrue();
    }
}
