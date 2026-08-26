package canopica.api.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.api.AbstractApiTest;
import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import canopica.api.determination.DeterminationService;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The Postgres container backing {@link AbstractPostgresTest} is a JVM-wide singleton, so the case list
 * this suite hits is never empty or exclusively this test's data -- every assertion below finds its own
 * fixture by id rather than assuming list length or position.
 *
 * <p>Caseload-scoped authorization (Task 2, design doc §2.1) is exercised here rather than in
 * {@code AuthorizationTest}, since it's a data-driven {@code case_assignment} check, not a role gate.
 */
class WorkerCaseControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired DeterminationService determinationService;
    @Autowired ObjectMapper objectMapper;

    @Test
    void caseListReturnsOneRowPerProgramRequestWithHeadNameStatusAndLatestDetermination() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String response = mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode myCase = findByProgramRequestId(response, ids.programRequestId());
        assertThat(myCase).as("case list should include the program request just created").isNotNull();
        assertThat(myCase.get("householdHeadName").asText()).isEqualTo("Dana Reyes");
        assertThat(myCase.get("status").asText()).isEqualTo("SUBMITTED");
        assertThat(myCase.get("latestDetermination").get("eligible").asBoolean()).isTrue();
    }

    @Test
    void everyMoneyFieldCrossesTheWireAsAStringNotAJsonNumber() throws Exception {
        // types.ts has claimed `benefitAmount: string` since Phase 1a, and until this test it was simply
        // untrue: Jackson serialises BigDecimal as a JSON number by default, so the browser parsed it into a
        // double. The visible cost is cents: a $649.00 award renders as "$649/month", because JSON.parse
        // turns 649.00 into 649 and the trailing zeros are gone before any component sees them. The
        // invariant this repo states everywhere -- money never round-trips through a float -- was true of
        // the database, the rules engine and the DTOs, and false at exactly the last hop.
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String detail = mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String list = mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode fromDetail = objectMapper.readTree(detail).get("determinations").get(0).get("benefitAmount");
        JsonNode fromList = findByProgramRequestId(list, ids.programRequestId())
                .get("latestDetermination").get("benefitAmount");

        assertThat(fromDetail.isTextual()).as("determination benefitAmount as JSON string").isTrue();
        assertThat(fromList.isTextual()).as("case-list benefitAmount as JSON string").isTrue();
        // Scale preserved exactly as the database stored it -- the whole point of the string.
        assertThat(fromDetail.asText()).contains(".");
    }

    @Test
    void caseDetailReturnsDeterminationHistoryNewestFirstAndAppendsCaseViewedAudit() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID firstId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
        UUID secondId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 20), LocalDate.of(2025, 6, 1), "SYSTEM");

        mvc.perform(get("/api/program-requests/" + ids.programRequestId()).header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.determinations.length()").value(2))
                .andExpect(jsonPath("$.determinations[0].determinationId").value(secondId.toString()))
                .andExpect(jsonPath("$.determinations[1].determinationId").value(firstId.toString()));

        assertThat(jdbc.queryForObject(
                "select count(*) from audit_event where event_type = 'CASE_VIEWED' and subject_id = ?",
                Integer.class, ids.programRequestId())).isEqualTo(1);
    }

    @Test
    void traceEndpointReturnsTheSameDecisionNamesTheDmnModelDefines() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String response = mvc.perform(get("/api/determinations/" + determinationId + "/trace")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertThat(response).contains("Excess Shelter Deduction", "Net Income", "Benefit Amount");
        assertThat(response).contains("\"policyParameterVersion\":\"SNAP-FY2025\"");
    }

    @Test
    void workerViewingAnUnassignedHouseholdAutoClaimsItAndIsMarkedInAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk());

        UUID samWorkerId = provisionedWorkerId("worker.sam@canopica.local");
        assertThat(jdbc.queryForObject(
                "select worker_id from case_assignment where household_id = ?", UUID.class, ids.householdId()))
                .isEqualTo(samWorkerId);
        assertThat(jdbc.queryForObject(
                "select payload->>'in_assignment' from audit_event "
                        + "where event_type = 'CASE_VIEWED' and subject_id = ?",
                String.class, ids.programRequestId())).isEqualTo("true");
    }

    @Test
    void workerNotHoldingTheActiveAssignmentGets403() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), otherWorkerId);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void supervisorViewingAnUnassignedHouseholdIsAllowedButNotMarkedInAssignmentAndDoesNotClaimIt() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk());

        assertThat(jdbc.queryForObject(
                "select count(*) from case_assignment where household_id = ?", Integer.class, ids.householdId()))
                .as("a supervisor's view is an override, not a claim -- it must not create an assignment")
                .isEqualTo(0);
        assertThat(jdbc.queryForObject(
                "select payload->>'in_assignment' from audit_event "
                        + "where event_type = 'CASE_VIEWED' and subject_id = ?",
                String.class, ids.programRequestId())).isEqualTo("false");
    }

    private JsonNode findByProgramRequestId(String listResponse, UUID programRequestId) throws Exception {
        for (JsonNode node : objectMapper.readTree(listResponse)) {
            if (node.get("programRequestId").asText().equals(programRequestId.toString())) {
                return node;
            }
        }
        return null;
    }

    // KeycloakWorkerSyncFilter provisions the worker row lazily, on that user's first authenticated
    // request -- looking it up by the seeded realm user's own email (unique, stable) rather than decoding
    // the JWT's sub claim ourselves.
    private UUID provisionedWorkerId(String email) {
        return jdbc.queryForObject("select id from worker where email = ?", UUID.class, email);
    }
}
