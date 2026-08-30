package canopica.api.caseload;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import canopica.api.api.dto.AtRiskCaseResponse;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Exercises {@link AtRiskCaseQuery} against a real Postgres -- a real days-remaining computation against
 * SNAP's 7-day-expedited/30-day standard (the same standard {@code mart_processing_timeliness.sql} applies to
 * decided cases), correctly scoped to still-pending cases only.
 */
class AtRiskCaseQueryTest extends AbstractPostgresTest {

    @Autowired AtRiskCaseQuery atRiskCaseQuery;
    @Autowired JdbcTemplate jdbc;

    @Test
    void agesAStandardCaseAgainstThe30DayStandardAndAnExpeditedCaseAgainstThe7DayStandard() {
        UUID standardId = createProgramRequest(LocalDate.now().minusDays(10), false, "SUBMITTED");
        UUID expeditedId = createProgramRequest(LocalDate.now().minusDays(3), true, "PENDING_VERIFICATION");

        List<AtRiskCaseResponse> queue = atRiskCaseQuery.findAtRiskCases();

        assertThat(byId(queue, standardId).daysRemaining()).isEqualTo(20);
        assertThat(byId(queue, expeditedId).daysRemaining()).isEqualTo(4);
    }

    @Test
    void excludesDeterminedAndWithdrawnRequests() {
        UUID determinedId = createProgramRequest(LocalDate.now().minusDays(1), false, "DETERMINED");
        UUID withdrawnId = createProgramRequest(LocalDate.now().minusDays(1), false, "WITHDRAWN");

        List<AtRiskCaseResponse> queue = atRiskCaseQuery.findAtRiskCases();

        assertThat(queue).extracting(AtRiskCaseResponse::programRequestId)
                .doesNotContain(determinedId, withdrawnId);
    }

    @Test
    void ordersMostUrgentFirstAndSurfacesAPreGeneratedStallReasonWhenOneExists() {
        UUID urgentId = createProgramRequest(LocalDate.now().minusDays(25), false, "SUBMITTED");
        UUID lessUrgentId = createProgramRequest(LocalDate.now().minusDays(5), false, "SUBMITTED");
        jdbc.update(
                "insert into sla_stall_reason (program_request_id, reason) values (?, ?)",
                urgentId, "awaiting INCOME verification, due in 5 days, last worker action 6 days ago");

        List<AtRiskCaseResponse> queue = atRiskCaseQuery.findAtRiskCases();

        assertThat(queue.indexOf(byId(queue, urgentId))).isLessThan(queue.indexOf(byId(queue, lessUrgentId)));
        assertThat(byId(queue, urgentId).stallReason())
                .isEqualTo("awaiting INCOME verification, due in 5 days, last worker action 6 days ago");
        assertThat(byId(queue, urgentId).stallReasonGeneratedAt()).isNotNull();
        assertThat(byId(queue, lessUrgentId).stallReason()).isNull();
    }

    private AtRiskCaseResponse byId(List<AtRiskCaseResponse> queue, UUID programRequestId) {
        return queue.stream().filter(item -> item.programRequestId().equals(programRequestId)).findFirst()
                .orElseThrow(() -> new AssertionError("no at-risk row for " + programRequestId));
    }

    private UUID createProgramRequest(LocalDate requestedOn, boolean isExpedited, String status) {
        UUID programRequestId = CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId();
        jdbc.update(
                "update program_request set requested_on = ?, is_expedited = ?, status = ? where id = ?",
                requestedOn, isExpedited, status, programRequestId);
        return programRequestId;
    }
}
