package canopica.portal.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.portal.AbstractApiTest;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Row-level authorization for the citizen's own read views (design doc §2.2), the same three-case shape
 * Phase 1b's own worker-side caseload tests already use for row-level auth: owner reads their own data
 * (200), a different owner's token against the same resource is denied (403), no token at all is denied
 * (401). The determination under test is a real one, decided by the real DMN engine through the ordinary
 * worker determination endpoint -- not a seeded fixture -- so the trace this test reads back is the same
 * kind of trace {@code answer_denial()} (Task 2, Python side) will actually consume.
 */
class CitizenDeterminationAccessTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void aCitizenCanReadTheirOwnDeterminationTrace() throws Exception {
        UUID determinationId = decideARealDetermination();

        mvc.perform(get("/api/my/determinations/" + determinationId + "/trace")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.dmnModelHash").isNotEmpty())
                .andExpect(jsonPath("$.policyParameterVersion").isNotEmpty());
    }

    @Test
    void aDifferentCitizensTokenIsForbiddenFromReadingTheDeterminationTrace() throws Exception {
        UUID determinationId = decideARealDetermination();

        mvc.perform(get("/api/my/determinations/" + determinationId + "/trace")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + otherCitizenToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void anUnauthenticatedRequestForADeterminationTraceIsUnauthorized() throws Exception {
        UUID determinationId = decideARealDetermination();

        mvc.perform(get("/api/my/determinations/" + determinationId + "/trace"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aCitizensProgramRequestListIncludesTheirOwnSubmissionAndNoOneElses() throws Exception {
        UUID ownProgramRequestId = submitAsCitizen(citizenToken());
        UUID otherProgramRequestId = submitAsCitizen(otherCitizenToken());

        String response = mvc.perform(get("/api/my/program-requests")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        var ids = objectMapper.readTree(response).findValuesAsText("programRequestId");
        assertThat(ids).contains(ownProgramRequestId.toString());
        assertThat(ids).doesNotContain(otherProgramRequestId.toString());
    }

    private UUID decideARealDetermination() throws Exception {
        UUID programRequestId = submitAsCitizen(citizenToken());

        // Household members' effective-dating starts at intake time (real Clock, real "today"), so asOfDate
        // must be today or later -- an older hardcoded date (as AuthorizationTest's request bodies use,
        // fine there since those never reach real DMN evaluation) sees zero effective members as of that
        // date and fails with a household-size-0 error, not a security-layer response.
        LocalDate today = LocalDate.now();
        String body = String.format(
                "{\"asOfDate\":\"%s\",\"benefitMonth\":\"%s\"}", today, today.withDayOfMonth(1));

        String response = mvc.perform(post("/api/program-requests/" + programRequestId + "/determinations")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        return UUID.fromString(objectMapper.readTree(response).get("determinationId").asText());
    }

    private UUID submitAsCitizen(String token) throws Exception {
        String response = mvc.perform(post("/api/applications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(TestPayloads.threePersonWorkingHouseholdIntake()))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return UUID.fromString(objectMapper.readTree(response).get("programRequestId").asText());
    }
}
