package canopica.portal.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.portal.AbstractApiTest;
import canopica.portal.policy.ParameterProposalDraft;
import canopica.portal.policy.ProposedParameterValue;
import canopica.portal.policy.RuleAuthoringClient;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
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
 * The HTTP contract for rule-authoring review, and the role gate in front of it.
 *
 * <p>The role cases carry most of the weight: {@code /api/policy/**} is the only ADMIN-only surface in this
 * system, and it is the surface that publishes the figures every future determination resolves against. A
 * SUPERVISOR reaching it would not look like a bug on any screen.
 */
@Import(PolicyParameterProposalControllerTest.FixedCopilot.class)
class PolicyParameterProposalControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;

    private static final String EXCERPT = "{\"documentExcerpt\":\"The maximum allotment rises to $305.\"}";

    @Test
    void anAdminCanDraftAProposalAgainstTheSetInForce() throws Exception {
        mvc.perform(post("/api/policy/proposals")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EXCERPT))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.currentVersionLabel").value("SNAP-FY2026"))
                // The reviewer/proposer identity comes from the token, never the body -- a caller cannot name
                // someone else as the person accountable for a benefit figure.
                .andExpect(jsonPath("$.proposedBy").isNotEmpty())
                .andExpect(jsonPath("$.generationModel").value("stub-model"));
    }

    @Test
    void theDiffIsRenderedAsRealJsonWithMoneyAsStrings() throws Exception {
        String body = mvc.perform(post("/api/policy/proposals")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EXCERPT))
                .andReturn().getResponse().getContentAsString();

        JsonNode change = objectMapper.readTree(body).get("proposedValues").get(0);
        // @JsonRawValue on the DTO means this has to be an array, not a string containing an array -- easy to
        // get wrong, and it would land on the browser as an unreadable blob rather than a diff.
        assertThat(objectMapper.readTree(body).get("proposedValues").isArray()).isTrue();
        assertThat(change.get("oldValue").isTextual()).isTrue();
        assertThat(change.get("oldValue").asText()).isEqualTo("298");
        assertThat(change.get("newValue").asText()).isEqualTo("305");
    }

    @Test
    void rejectingAProposalRecordsTheReviewerAndPublishesNothing() throws Exception {
        UUID proposalId = draftProposal();

        mvc.perform(post("/api/policy/proposals/" + proposalId + "/review")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"accept\":false}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("REJECTED"))
                .andExpect(jsonPath("$.reviewedBy").isNotEmpty())
                .andExpect(jsonPath("$.publishedParameterSetId").doesNotExist());
    }

    @Test
    void acceptingWithoutPublicationDetailsIsRejectedRatherThanGuessedAt() throws Exception {
        // An effective date is a policy fact stated by the memo. Defaulting it to "today" would publish a
        // parameter version on a date nobody chose.
        UUID proposalId = draftProposal();

        mvc.perform(post("/api/policy/proposals/" + proposalId + "/review")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"accept\":true}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void anEmptyExcerptIsRejected() throws Exception {
        mvc.perform(post("/api/policy/proposals")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"documentExcerpt\":\"   \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void aSupervisorIsForbiddenFromDraftingAProposal() throws Exception {
        mvc.perform(post("/api/policy/proposals")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EXCERPT))
                .andExpect(status().isForbidden());
    }

    @Test
    void aWorkerIsForbiddenFromReviewingAProposal() throws Exception {
        mvc.perform(post("/api/policy/proposals/" + UUID.randomUUID() + "/review")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"accept\":false}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aWorkerIsForbiddenFromEvenListingProposals() throws Exception {
        // Listing is gated too: a pending diff names the figures someone is thinking of changing, which is
        // not caseload information and has no reason to be visible outside the role that decides it.
        mvc.perform(get("/api/policy/proposals").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void aCitizenTokenCannotReachThisSurfaceAtAll() throws Exception {
        // 401 rather than 403: a citizens-realm token isn't signed by the workers realm's key, so it fails
        // at authentication before any role check runs (same reasoning as AuthorizationTest's own cases).
        mvc.perform(get("/api/policy/proposals").header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken()))
                .andExpect(status().isUnauthorized());
    }

    private UUID draftProposal() throws Exception {
        String body = mvc.perform(post("/api/policy/proposals")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EXCERPT))
                .andReturn().getResponse().getContentAsString();
        return UUID.fromString(objectMapper.readTree(body).get("id").asText());
    }

    /** Always the same one-line diff -- this class is testing the HTTP surface, not the model. */
    @TestConfiguration
    static class FixedCopilot {

        @Bean
        @Primary
        RuleAuthoringClient fixedCopilot() {
            return (excerpt, setId, currentValues) -> new ParameterProposalDraft(
                    setId,
                    List.of(new ProposedParameterValue("MAX_ALLOTMENT", 1, new BigDecimal("298"),
                            new BigDecimal("305"), "USD_PER_MONTH", "stated by the memo")),
                    excerpt,
                    "stub-model",
                    "v1");
        }
    }
}
