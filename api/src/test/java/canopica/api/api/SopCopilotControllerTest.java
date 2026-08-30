package canopica.api.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import canopica.api.sop.SopAnswer;
import canopica.api.sop.SopCopilotClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The role gate and request/response contract for the SOP Copilot's ask endpoint. Stubs {@link
 * SopCopilotClient} via a {@code @TestConfiguration} bean rather than a mock HTTP server -- the same pattern
 * {@code PolicyParameterProposalControllerTest} already establishes for {@link
 * canopica.api.policy.RuleAuthoringClient}, a different AI-capability interface with the identical
 * "unreachable model, deterministic test" motivation. There is no separate dedicated test for {@code
 * HttpSopCopilotClient} itself, matching the real, existing precedent this codebase already has for {@code
 * HttpRuleAuthoringClient} -- its own HTTP behavior has no dedicated test either, only this same
 * stub-interface shape at the controller layer.
 */
@Import(SopCopilotControllerTest.StubSopCopilotConfig.class)
class SopCopilotControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;

    @Test
    void askRejectsACitizenRealmToken() throws Exception {
        // A citizen-realm token fails JWT validation against the worker chain's own JWKS/issuer
        // (different Keycloak realm entirely) -- 401 (unverifiable token), not 403 (valid token,
        // insufficient role).
        mvc.perform(post("/api/sop-copilot/ask")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"test\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void askIsOkForAWorkerAndReturnsTheStubbedAnswer() throws Exception {
        mvc.perform(post("/api/sop-copilot/ask")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"How fast must an expedited case be decided?\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("Within 7 days."))
                .andExpect(jsonPath("$.abstained").value(false))
                .andExpect(jsonPath("$.citations[0]").value("new_application -- Expedited service screening"));
    }

    @Test
    void askIsOkForASupervisor() throws Exception {
        mvc.perform(post("/api/sop-copilot/ask")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"test\"}"))
                .andExpect(status().isOk());
    }

    @TestConfiguration
    static class StubSopCopilotConfig {
        @Bean
        @Primary
        SopCopilotClient stubSopCopilotClient() {
            return question -> new SopAnswer(
                    "Within 7 days.", java.util.List.of("new_application -- Expedited service screening"), false);
        }
    }
}
