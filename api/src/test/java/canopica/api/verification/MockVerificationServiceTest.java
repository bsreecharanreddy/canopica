package canopica.api.verification;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class MockVerificationServiceTest extends AbstractPostgresTest {

    @Autowired MockVerificationService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void theSamePersonAndDataElementAlwaysResolveToTheSameOutcome() {
        UUID personId = UUID.randomUUID();

        String first = service.resolveOutcome(personId, "INCOME");
        String second = service.resolveOutcome(personId, "INCOME");

        assertThat(first).isEqualTo(second);
    }

    @Test
    void allThreeOutcomesAreReachableAcrossARangeOfSyntheticInputs() {
        Set<String> outcomes = new HashSet<>();
        for (int i = 0; i < 30; i++) {
            outcomes.add(service.resolveOutcome(UUID.randomUUID(), "INCOME"));
        }

        assertThat(outcomes).containsExactlyInAnyOrder("MATCHES", "DISCREPANCY", "UNAVAILABLE");
    }

    @Test
    void requestVerificationResolvesSynchronouslyAndUpdatesVerificationStatus() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");
        String expectedOutcome = service.resolveOutcome(ids.headPersonId(), "INCOME");

        UUID responseId = service.requestVerification(verificationId, "worker-1");

        var verificationRow = jdbc.queryForMap(
                "select status, satisfied_on from verification where id = ?", verificationId);
        assertThat(verificationRow.get("status")).isEqualTo("RECEIVED");
        assertThat(verificationRow.get("satisfied_on")).isNotNull();

        var responseRow = jdbc.queryForMap(
                "select verification_id, outcome, raw_payload from verification_response where id = ?", responseId);
        assertThat(responseRow.get("verification_id")).isEqualTo(verificationId);
        assertThat(responseRow.get("outcome")).isEqualTo(expectedOutcome);
        assertThat(responseRow.get("raw_payload").toString()).contains("MOCK_EXTERNAL_VERIFICATION_SERVICE");
    }

    @Test
    void requestVerificationAppendsRequestedThenReceivedAuditEventsInOrder() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");

        service.requestVerification(verificationId, "worker-1");

        var events = jdbc.queryForList(
                "select payload from audit_event where event_type = 'VERIFICATION_UPDATED' "
                        + "and subject_id = ? order by id",
                verificationId);
        assertThat(events).hasSize(2);
        // jsonb::text is Postgres's own canonical form (space after ':' and ',', see V6's own comment on
        // audit_event_chain()) -- not Jackson's compact serialization, which is what the app actually sent.
        assertThat(events.get(0).get("payload").toString()).contains("\"stage\": \"REQUESTED\"");
        assertThat(events.get(1).get("payload").toString()).contains("\"stage\": \"RECEIVED\"");
    }
}
