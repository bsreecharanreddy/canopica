package canopica.portal.domain;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.portal.AbstractPostgresTest;
import canopica.portal.repo.IncomeRecordRepository;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Proves the effective-dating mapping (V1/V2) and the repositories' as-of
 * queries agree with each other, not just that each compiles. This is the
 * property Task 5's fact assembly depends on: an as-of query for a date
 * before a record's effective_from, or after its effective_to, must exclude
 * it; a query landing inside an open-ended span must include it.
 */
class AsOfQueryTest extends AbstractPostgresTest {

    @Autowired IncomeRecordRepository incomeRecords;
    @Autowired JdbcTemplate jdbc;

    @Test
    void excludesARecordNotYetEffectiveAndIncludesAnOpenEndedOne() {
        UUID personId = insertPerson();

        jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, "
                        + "monthly_amount, effective_from, effective_to) "
                        + "values (?, ?, 'WAGES', true, 1500.00, date '2025-01-01', null)",
                UUID.randomUUID(), personId);
        jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, "
                        + "monthly_amount, effective_from, effective_to) "
                        + "values (?, ?, 'WAGES', true, 2100.00, date '2025-07-01', null)",
                UUID.randomUUID(), personId);

        List<IncomeRecord> juneRecords =
                incomeRecords.findEffectiveOn(List.of(personId), LocalDate.of(2025, 6, 15));

        assertThat(juneRecords).hasSize(1);
        assertThat(juneRecords.get(0).getMonthlyAmount()).isEqualByComparingTo(new BigDecimal("1500.00"));
    }

    @Test
    void excludesARecordWhoseEffectiveRangeHasClosed() {
        UUID personId = insertPerson();

        jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, "
                        + "monthly_amount, effective_from, effective_to) "
                        + "values (?, ?, 'WAGES', true, 1200.00, date '2024-01-01', date '2024-12-31')",
                UUID.randomUUID(), personId);

        List<IncomeRecord> juneRecords =
                incomeRecords.findEffectiveOn(List.of(personId), LocalDate.of(2025, 6, 15));

        assertThat(juneRecords).isEmpty();
    }

    private UUID insertPerson() {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
                        + "values (?, 'Test', 'Person', date '1990-01-01', ?, 'X')",
                id, "tok-" + id);
        return id;
    }
}
