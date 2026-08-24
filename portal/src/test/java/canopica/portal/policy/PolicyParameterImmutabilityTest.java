package canopica.portal.policy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.portal.AbstractPostgresTest;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * Proves immutability is enforced by the database, not just by application convention -- the V3 migration's
 * trigger refuses UPDATE/DELETE outright.
 *
 * <p>V15 narrowed that refusal by exactly one case, so that a superseding parameter set can close the one it
 * supersedes (see {@code docs/design/2026-08-23-policy-parameter-supersession.md}). The tests below are the
 * boundary of that narrowing: it is one-way ({@code null} to a date, never back), one-shot (a closed range
 * cannot move), and total on every other column (a close that smuggles in any other edit is still refused).
 * A narrowing nobody pins is a narrowing that widens.
 */
class PolicyParameterImmutabilityTest extends AbstractPostgresTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void refusesToUpdateAPublishedParameter() {
        assertThatThrownBy(() -> jdbc.update(
                "update policy_parameter set numeric_value = 999 where name = 'MINIMUM_BENEFIT'"))
                .hasMessageContaining("immutable once published");
    }

    @Test
    void refusesToDeleteAPublishedParameterSet() {
        assertThatThrownBy(() -> jdbc.update(
                "delete from policy_parameter_set where version_label = 'SNAP-FY2025'"))
                .hasMessageContaining("immutable once published");
    }

    /**
     * Operates on a set this test inserts itself, and rolls back -- closing the real seeded FY2026 set would
     * leak into every other test sharing this JVM's singleton container.
     */
    @Test
    @Transactional
    void allowsClosingAnOpenEndedRange() {
        UUID id = insertOpenEndedSet("SNAP-TEST-CLOSEABLE", LocalDate.of(2099, 1, 1));

        jdbc.update("update policy_parameter_set set effective_to = ? where id = ?",
                LocalDate.of(2099, 6, 30), id);

        LocalDate closedAt = jdbc.queryForObject(
                "select effective_to from policy_parameter_set where id = ?", LocalDate.class, id);
        assertThat(closedAt).isEqualTo(LocalDate.of(2099, 6, 30));
    }

    @Test
    void refusesToMoveARangeThatIsAlreadyClosed() {
        // FY2025 is seeded closed at 2025-09-30. Moving that boundary would silently change which parameter
        // set a *new* determination in that window resolves to.
        assertThatThrownBy(() -> jdbc.update(
                "update policy_parameter_set set effective_to = date '2026-01-01' "
                        + "where version_label = 'SNAP-FY2025'"))
                .hasMessageContaining("immutable once published");
    }

    @Test
    void refusesToReopenAClosedRange() {
        assertThatThrownBy(() -> jdbc.update(
                "update policy_parameter_set set effective_to = null where version_label = 'SNAP-FY2025'"))
                .hasMessageContaining("immutable once published");
    }

    @Test
    void refusesACloseThatAlsoEditsAnyOtherColumn() {
        // The whole safety of the narrowing rests on this: if a close could carry another edit along with it,
        // "immutable once published" would be enforcing nothing at all.
        assertThatThrownBy(() -> jdbc.update(
                "update policy_parameter_set set effective_to = date '2026-09-30', source_citation = 'edited' "
                        + "where version_label = 'SNAP-FY2026'"))
                .hasMessageContaining("immutable once published");
    }

    private UUID insertOpenEndedSet(String versionLabel, LocalDate effectiveFrom) {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into policy_parameter_set "
                        + "(id, program_code, version_label, effective_from, effective_to, source_citation, retrieved_on) "
                        + "values (?, 'SNAP', ?, ?, null, 'test fixture', ?)",
                id, versionLabel, effectiveFrom, LocalDate.of(2026, 8, 23));
        return id;
    }
}
