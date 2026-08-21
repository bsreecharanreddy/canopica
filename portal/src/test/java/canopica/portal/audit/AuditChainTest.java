package canopica.portal.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.portal.AbstractPostgresTest;
import canopica.portal.CaseFixtures;
import canopica.portal.determination.DeterminationService;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class AuditChainTest extends AbstractPostgresTest {

    @Autowired AuditService audit;
    @Autowired DeterminationService determinationService;
    @Autowired JdbcTemplate jdbc;

    @Test
    void firstEventChainsFromTheZeroHash() {
        audit.append(AuditEventType.CASE_VIEWED, "worker-1", "household", UUID.randomUUID(), Map.of());

        assertThat(jdbc.queryForObject(
                "select prev_hash from audit_event order by id limit 1", String.class))
                .isEqualTo("0".repeat(64));
    }

    @Test
    void eachEventChainsFromItsPredecessor() {
        for (int i = 0; i < 5; i++) {
            audit.append(AuditEventType.CASE_VIEWED, "worker-1", "household",
                    UUID.randomUUID(), Map.of("seq", i));
        }

        var rows = jdbc.queryForList("select id, prev_hash, hash from audit_event order by id");
        for (int i = 1; i < rows.size(); i++) {
            assertThat(rows.get(i).get("prev_hash")).isEqualTo(rows.get(i - 1).get("hash"));
        }
    }

    @Test
    void refusesUpdateAndDelete() {
        audit.append(AuditEventType.CASE_VIEWED, "worker-1", "household", UUID.randomUUID(), Map.of());

        assertThatThrownBy(() -> jdbc.update("update audit_event set actor_id = 'x'"))
                .hasMessageContaining("append-only");
        assertThatThrownBy(() -> jdbc.update("delete from audit_event"))
                .hasMessageContaining("append-only");
    }

    @Test
    void everyDeterminationAppendsExactlyOneAuditEvent() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        UUID determinationId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        List<Map<String, Object>> events = jdbc.queryForList(
                "select event_type, subject_id, payload from audit_event where event_type = 'DETERMINATION_MADE'");
        assertThat(events).hasSize(1);
        assertThat(events.get(0).get("subject_id")).isEqualTo(determinationId);
        assertThat(events.get(0).get("payload").toString()).contains("policyParameterVersion");
    }
}
