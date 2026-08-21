package ies.portal.domain;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ies.portal.AbstractPostgresTest;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * The effective-dating and benefit-month invariants are enforced by database
 * constraints, not application code — proved here against a real Postgres
 * instance rather than assumed from reading the migration.
 */
class EffectiveDatingConstraintTest extends AbstractPostgresTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void rejectsAnEffectiveToBeforeItsEffectiveFrom() {
        UUID personId = insertPerson();
        assertThatThrownBy(() -> jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, "
                        + "monthly_amount, effective_from, effective_to) "
                        + "values (?, ?, 'WAGES', true, 1000.00, date '2026-03-01', date '2026-02-01')",
                UUID.randomUUID(), personId))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void rejectsABenefitMonthThatIsNotTheFirstOfTheMonth() {
        UUID requestId = insertProgramRequest();
        assertThatThrownBy(() -> jdbc.update(
                "insert into benefit_month (id, program_request_id, benefit_month) "
                        + "values (?, ?, date '2026-03-15')",
                UUID.randomUUID(), requestId))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void allowsAnOpenEndedEffectiveRange() {
        UUID personId = insertPerson();
        jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, "
                        + "monthly_amount, effective_from, effective_to) "
                        + "values (?, ?, 'WAGES', true, 1000.00, date '2026-01-01', null)",
                UUID.randomUUID(), personId);
        // No exception is the assertion: an open-ended (still in effect) span is valid.
    }

    private UUID insertPerson() {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
                        + "values (?, 'Test', 'Person', date '1990-01-01', ?, 'X')",
                id, "tok-" + id);
        return id;
    }

    private UUID insertProgramRequest() {
        UUID personId = insertPerson();
        UUID householdId = UUID.randomUUID();
        jdbc.update(
                "insert into household (id, head_person_id, county, address_line1, city, state, zip_code) "
                        + "values (?, ?, 'Test County', '123 Test St', 'Testville', 'TS', '00000')",
                householdId, personId);
        UUID applicationId = UUID.randomUUID();
        jdbc.update(
                "insert into application (id, household_id, submitted_at, channel) "
                        + "values (?, ?, now(), 'ONLINE')",
                applicationId, householdId);
        UUID requestId = UUID.randomUUID();
        jdbc.update(
                "insert into program_request (id, application_id, program_code, status, requested_on) "
                        + "values (?, ?, 'SNAP', 'SUBMITTED', current_date)",
                requestId, applicationId);
        return requestId;
    }
}
