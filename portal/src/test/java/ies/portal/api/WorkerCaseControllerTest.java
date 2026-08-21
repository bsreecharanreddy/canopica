package ies.portal.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import ies.portal.AbstractPostgresTest;
import ies.portal.CaseFixtures;
import ies.portal.determination.DeterminationService;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The Postgres container backing {@link AbstractPostgresTest} is a JVM-wide singleton, so the case list
 * this suite hits is never empty or exclusively this test's data -- every assertion below finds its own
 * fixture by id rather than assuming list length or position.
 */
class WorkerCaseControllerTest extends AbstractPostgresTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired DeterminationService determinationService;
    @Autowired ObjectMapper objectMapper;

    @Test
    void caseListReturnsOneRowPerProgramRequestWithHeadNameStatusAndLatestDetermination() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String response = mvc.perform(get("/api/worker/cases").header("X-IES-Role", "WORKER"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode myCase = findByProgramRequestId(response, ids.programRequestId());
        assertThat(myCase).as("case list should include the program request just created").isNotNull();
        assertThat(myCase.get("householdHeadName").asText()).isEqualTo("Dana Reyes");
        assertThat(myCase.get("status").asText()).isEqualTo("SUBMITTED");
        assertThat(myCase.get("latestDetermination").get("eligible").asBoolean()).isTrue();
    }

    @Test
    void caseDetailReturnsDeterminationHistoryNewestFirstAndAppendsCaseViewedAudit() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID firstId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
        UUID secondId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 20), LocalDate.of(2025, 6, 1), "SYSTEM");

        mvc.perform(get("/api/program-requests/" + ids.programRequestId()).header("X-IES-Role", "WORKER"))
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
                        .header("X-IES-Role", "WORKER"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertThat(response).contains("Excess Shelter Deduction", "Net Income", "Benefit Amount");
        assertThat(response).contains("\"policyParameterVersion\":\"SNAP-FY2025\"");
    }

    private JsonNode findByProgramRequestId(String listResponse, UUID programRequestId) throws Exception {
        for (JsonNode node : objectMapper.readTree(listResponse)) {
            if (node.get("programRequestId").asText().equals(programRequestId.toString())) {
                return node;
            }
        }
        return null;
    }
}
