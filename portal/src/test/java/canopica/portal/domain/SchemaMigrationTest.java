package canopica.portal.domain;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.portal.AbstractPostgresTest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class SchemaMigrationTest extends AbstractPostgresTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void everyPhase1aOperationalTableExists() {
        List<String> tables = jdbc.queryForList(
                "select table_name from information_schema.tables where table_schema = 'public'",
                String.class);
        assertThat(tables).contains(
                "person", "household", "household_member", "worker", "case_assignment",
                "application", "program_request", "income_record", "expense_record",
                "living_arrangement", "work_activity", "disability_record",
                "verification", "benefit_month");
    }

    @Test
    void householdCarriesTheCaseMailingAddress() {
        List<String> columns = jdbc.queryForList(
                "select column_name from information_schema.columns "
                        + "where table_schema = 'public' and table_name = 'household'",
                String.class);
        assertThat(columns).contains(
                "address_line1", "address_line2", "city", "state", "zip_code");
    }

    @Test
    void everyEffectiveDatedTableCarriesBothDateColumns() {
        List<String> effectiveDated = List.of(
                "household_member", "income_record", "expense_record",
                "living_arrangement", "work_activity", "disability_record",
                "case_assignment");
        for (String table : effectiveDated) {
            List<String> columns = jdbc.queryForList(
                    "select column_name from information_schema.columns "
                            + "where table_schema = 'public' and table_name = ?",
                    String.class, table);
            assertThat(columns)
                    .as("effective dating on %s", table)
                    .contains("effective_from", "effective_to");
        }
    }
}
