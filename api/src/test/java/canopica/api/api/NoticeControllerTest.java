package canopica.api.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import canopica.api.CaseFixtures;
import canopica.api.determination.DeterminationService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Exercises the real {@code /api/cases/notices/*} endpoints -- a real Postgres row, real caseload-scoping,
 * real PDF rendering ({@link canopica.api.notice.NoticePdfRenderer}'s own unit tests already prove the
 * rendering mechanism itself is correct; what matters here is that {@code approve} actually reaches it and
 * does not silently skip or swallow a failure -- an {@code IllegalStateException} on zero rendered bytes
 * would roll back the whole transaction and fail this test's own {@code status().isOk()} assertion).
 */
class NoticeControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper objectMapper;
    @Autowired DeterminationService determinations;

    @Test
    void reviewQueueIncludesOnlyThisWorkersOwnCaseloadsDraftNotices() throws Exception {
        mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk());
        UUID samWorkerId = jdbc.queryForObject(
                "select id from worker where email = ?", UUID.class, "worker.sam@canopica.local");

        var mine = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var notMine = CaseFixtures.threePersonWorkingHousehold(jdbc);
        CaseFixtures.insertCaseAssignment(jdbc, mine.householdId(), samWorkerId);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Not Sam", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, notMine.householdId(), otherWorkerId);

        UUID mineDeterminationId = determine(mine.programRequestId());
        UUID notMineDeterminationId = determine(notMine.programRequestId());
        UUID mineNoticeId = CaseFixtures.insertNotice(jdbc, mine.programRequestId(), mineDeterminationId, "APPROVAL");
        CaseFixtures.insertNotice(jdbc, notMine.programRequestId(), notMineDeterminationId, "APPROVAL");

        String response = mvc.perform(get("/api/cases/notices/review-queue")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode items = objectMapper.readTree(response);

        assertThat(indexOfNotice(items, mineNoticeId))
                .as("this worker's own draft notice must be present")
                .isNotEqualTo(-1);
        assertThat(items.size())
                .as("a notice from a household outside this worker's caseload must not appear")
                .isEqualTo(1);
    }

    @Test
    void approveIsForbiddenForAWorkerNotHoldingTheActiveAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else Approving", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), otherWorkerId);
        UUID determinationId = determine(ids.programRequestId());
        UUID noticeId = CaseFixtures.insertNotice(jdbc, ids.programRequestId(), determinationId, "APPROVAL");

        mvc.perform(post("/api/cases/notices/" + noticeId + "/approve")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());

        assertThat(jdbc.queryForObject("select status from notice where id = ?", String.class, noticeId))
                .isEqualTo("DRAFT");
    }

    @Test
    void approveRendersAPdfMarksTheNoticeSentAndAppendsBothAuditEventsInOrder() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determine(ids.programRequestId());
        UUID noticeId = CaseFixtures.insertNotice(jdbc, ids.programRequestId(), determinationId, "APPROVAL");

        mvc.perform(post("/api/cases/notices/" + noticeId + "/approve")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SENT"));

        var row = jdbc.queryForMap("select status, approved_by, approved_at, sent_at from notice where id = ?", noticeId);
        assertThat(row.get("status")).isEqualTo("SENT");
        // approved_by/rejected_by record the JWT's own `sub` claim (authentication.getName()), the same raw
        // Keycloak-subject value DocumentController's own confirm() passes through as actorId -- not the
        // worker's email, which findByKeycloakSubject's own lookup already proves this value maps back to.
        assertThat(row.get("approved_by")).isEqualTo(samKeycloakSubject());
        assertThat(row.get("approved_at")).isNotNull();
        assertThat(row.get("sent_at")).isNotNull();

        var auditRows = jdbc.queryForList(
                "select event_type from audit_event where subject_id = ? "
                        + "and event_type in ('NOTICE_APPROVED', 'NOTICE_SENT') order by id",
                ids.programRequestId());
        assertThat(auditRows).hasSize(2);
        assertThat(auditRows.get(0).get("event_type")).isEqualTo("NOTICE_APPROVED");
        assertThat(auditRows.get(1).get("event_type")).isEqualTo("NOTICE_SENT");
    }

    @Test
    void rejectLeavesTheNoticeRejectedWithNoSentEventAndRecordsTheRejector() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determine(ids.programRequestId());
        UUID noticeId = CaseFixtures.insertNotice(jdbc, ids.programRequestId(), determinationId, "DENIAL");

        mvc.perform(post("/api/cases/notices/" + noticeId + "/reject")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("REJECTED"));

        var row = jdbc.queryForMap(
                "select status, rejected_by, rejected_at, sent_at, approved_by from notice where id = ?", noticeId);
        assertThat(row.get("status")).isEqualTo("REJECTED");
        assertThat(row.get("rejected_by")).isEqualTo(samKeycloakSubject());
        assertThat(row.get("rejected_at")).isNotNull();
        assertThat(row.get("sent_at")).isNull();
        assertThat(row.get("approved_by")).isNull();

        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where subject_id = ? "
                                + "and event_type in ('NOTICE_APPROVED', 'NOTICE_SENT')",
                        Integer.class, ids.programRequestId()))
                .as("a rejection must never append the events reserved for a dispatched notice")
                .isEqualTo(0);
    }

    private String samKeycloakSubject() {
        return jdbc.queryForObject(
                "select keycloak_subject from worker where email = ?", String.class, "worker.sam@canopica.local");
    }

    private UUID determine(UUID programRequestId) {
        return determinations.determine(
                programRequestId, LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
    }

    private long indexOfNotice(JsonNode items, UUID noticeId) {
        long i = 0;
        for (JsonNode item : items) {
            if (item.get("noticeId").asText().equals(noticeId.toString())) {
                return i;
            }
            i++;
        }
        return -1;
    }
}
