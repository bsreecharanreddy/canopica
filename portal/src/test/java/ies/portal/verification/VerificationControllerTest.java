package ies.portal.verification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import ies.portal.AbstractApiTest;
import ies.portal.CaseFixtures;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Authorization and response-shape tests for the mocked verification interface (Task 3, design doc §2.2).
 * Reuses {@link ies.portal.caseload.CaseAssignmentService}'s exact caseload check, so the 403/claim/
 * SUPERVISOR-override behavior here mirrors {@code WorkerCaseControllerTest} deliberately.
 */
class VerificationControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void workerAutoClaimingAnUnassignedHouseholdCanRequestAndResolveAVerification() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");

        String response = mvc.perform(post("/api/program-requests/" + ids.programRequestId()
                        + "/verifications/" + verificationId + "/request")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("RECEIVED"))
                .andExpect(jsonPath("$.outcome").isNotEmpty())
                .andReturn().getResponse().getContentAsString();

        JsonNode node = objectMapper.readTree(response);
        assertThat(node.has("rawPayload")).as("raw mock payload must never reach the HTTP response").isFalse();
    }

    @Test
    void listReturnsStatusAndOutcomeButNeverRawPayload() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");

        mvc.perform(post("/api/program-requests/" + ids.programRequestId()
                        + "/verifications/" + verificationId + "/request")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk());

        String response = mvc.perform(get("/api/program-requests/" + ids.programRequestId() + "/verifications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertThat(response).doesNotContain("rawPayload", "MOCK_EXTERNAL_VERIFICATION_SERVICE");
        JsonNode list = objectMapper.readTree(response);
        assertThat(list).hasSize(1);
        assertThat(list.get(0).get("status").asText()).isEqualTo("RECEIVED");
        assertThat(list.get(0).get("outcome").asText()).isNotBlank();
    }

    @Test
    void workerNotHoldingTheActiveAssignmentGets403OnBothEndpoints() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else", "WORKER");
        jdbc.update(
                "insert into case_assignment (id, household_id, worker_id, effective_from) "
                        + "values (?, ?, ?, current_date)",
                UUID.randomUUID(), ids.householdId(), otherWorkerId);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId() + "/verifications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/program-requests/" + ids.programRequestId()
                        + "/verifications/" + verificationId + "/request")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void supervisorCanRequestAVerificationOnAnUnassignedHouseholdWithoutClaimingIt() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");

        mvc.perform(post("/api/program-requests/" + ids.programRequestId()
                        + "/verifications/" + verificationId + "/request")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk());

        assertThat(jdbc.queryForObject(
                        "select count(*) from case_assignment where household_id = ?", Integer.class, ids.householdId()))
                .as("a supervisor's action is an override, not a claim -- it must not create an assignment")
                .isEqualTo(0);
    }

    @Test
    void verificationIdNotBelongingToTheProgramRequestReturns404() throws Exception {
        var idsA = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var idsB = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationForB = CaseFixtures.insertVerification(jdbc, idsB.programRequestId(), "INCOME");

        mvc.perform(post("/api/program-requests/" + idsA.programRequestId()
                        + "/verifications/" + verificationForB + "/request")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isNotFound());
    }
}
