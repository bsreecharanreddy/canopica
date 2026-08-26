package canopica.api.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

class AuthorizationTest extends AbstractApiTest {

    @Autowired MockMvc mvc;

    // A citizen-realm token is signed by the citizens realm's own key, so the worker chain's decoder
    // (validating against the *workers* realm's issuer/JWKS) can't even verify the signature -- this fails
    // at authentication, before any role check runs, so it's 401 rather than 403. Same reasoning as
    // workerTokenCannotBeUsedAgainstTheCitizenOnlyIntakeEndpoint below, in the opposite direction.
    @Test
    void citizenTokenIsUnauthorizedAgainstTheWorkerCaseList() throws Exception {
        mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void citizenTokenIsUnauthorizedCreatingADetermination() throws Exception {
        mvc.perform(post("/api/program-requests/" + UUID.randomUUID() + "/determinations")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"asOfDate\":\"2025-06-15\",\"benefitMonth\":\"2025-06-01\"}"))
                .andExpect(status().isUnauthorized());
    }

    // Task 2 widened these role gates: a SUPERVISOR can view any case (design doc §2.1) -- the
    // caseload-scoped part of that (assigned WORKER vs. anyone else) is a data-driven check in
    // WorkerCaseController, not a role gate, so it isn't exercised here; this only proves the role itself
    // clears SecurityConfig's static check.
    @Test
    void supervisorTokenIsAuthorizedForTheWorkerCaseList() throws Exception {
        mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk());
    }

    // The genuine "authenticated, wrong role" 403 case post-Task-2: creating a determination is still
    // WORKER-only -- Task 2 did not widen this endpoint the way it widened case viewing.
    @Test
    void supervisorTokenIsForbiddenFromCreatingADetermination() throws Exception {
        mvc.perform(post("/api/program-requests/" + UUID.randomUUID() + "/determinations")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"asOfDate\":\"2025-06-15\",\"benefitMonth\":\"2025-06-01\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingBearerTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/worker/cases")).andExpect(status().isUnauthorized());
    }

    @Test
    void malformedBearerTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer not-a-real-jwt"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void workerTokenCannotBeUsedAgainstTheCitizenOnlyIntakeEndpoint() throws Exception {
        // A worker-realm token has the wrong issuer for the citizen chain entirely -- proves the two
        // resource-server chains are genuinely isolated by issuer, not just by a role check.
        mvc.perform(post("/api/applications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isUnauthorized());
    }
}
