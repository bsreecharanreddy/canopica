package ies.portal.policy;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ies.portal.AbstractPostgresTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Proves immutability is enforced by the database, not just by application
 * convention -- the V3 migration's trigger refuses UPDATE/DELETE outright.
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
}
