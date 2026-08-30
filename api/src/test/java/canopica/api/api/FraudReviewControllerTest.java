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
 * Exercises the real {@code /api/fraud/*} endpoints -- a real Postgres row, real SUPERVISOR-only
 * authorization, and a real assertion that neither review action ever touches the determination it flagged
 * (constraint 19).
 */
class FraudReviewControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper objectMapper;
    @Autowired DeterminationService determinations;

    @Test
    void reviewQueueIsForbiddenForAWorker() throws Exception {
        mvc.perform(get("/api/fraud/review-queue").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void reviewQueueOrdersUnreviewedFlagsHighestScoreFirstAndExcludesAlreadyReviewedOnes() throws Exception {
        var low = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var high = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var reviewed = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID lowId = CaseFixtures.insertFraudRiskScore(jdbc, low.programRequestId(), determine(low.programRequestId()), 0.3);
        UUID highId = CaseFixtures.insertFraudRiskScore(jdbc, high.programRequestId(), determine(high.programRequestId()), 0.9);
        UUID reviewedId = CaseFixtures.insertFraudRiskScore(
                jdbc, reviewed.programRequestId(), determine(reviewed.programRequestId()), 0.95);
        jdbc.update(
                "update fraud_risk_score set review_outcome = 'CLEARED', reviewed_by = 'someone', "
                        + "reviewed_at = now() where id = ?",
                reviewedId);

        String response = mvc.perform(get("/api/fraud/review-queue")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode items = objectMapper.readTree(response);

        assertThat(items.size()).isEqualTo(2);
        assertThat(items.get(0).get("id").asText()).isEqualTo(highId.toString());
        assertThat(items.get(1).get("id").asText()).isEqualTo(lowId.toString());
    }

    @Test
    void confirmSetsReviewOutcomeAppendsAnAuditEventAndNeverTouchesTheDetermination() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determine(ids.programRequestId());
        UUID scoreId = CaseFixtures.insertFraudRiskScore(jdbc, ids.programRequestId(), determinationId, 0.9);
        String originalBenefitAmount = jdbc.queryForObject(
                "select benefit_amount::text from eligibility_determination where id = ?", String.class, determinationId);

        mvc.perform(post("/api/fraud/" + scoreId + "/confirm")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reviewOutcome").value("CONFIRMED_RISK"))
                .andExpect(jsonPath("$.reviewedBy").value(robinKeycloakSubject()));

        assertThat(jdbc.queryForObject("select review_outcome from fraud_risk_score where id = ?", String.class, scoreId))
                .isEqualTo("CONFIRMED_RISK");
        assertThat(jdbc.queryForObject(
                        "select benefit_amount::text from eligibility_determination where id = ?", String.class, determinationId))
                .as("confirming a fraud flag must never change the determination it flagged")
                .isEqualTo(originalBenefitAmount);
        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where event_type = 'FRAUD_FLAG_REVIEWED' and subject_id = ?",
                        Integer.class, determinationId))
                .isEqualTo(1);
    }

    @Test
    void clearSetsReviewOutcomeAndDoesNotRaiseAnAdditionalFlagEvent() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determine(ids.programRequestId());
        UUID scoreId = CaseFixtures.insertFraudRiskScore(jdbc, ids.programRequestId(), determinationId, 0.9);

        mvc.perform(post("/api/fraud/" + scoreId + "/clear")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reviewOutcome").value("CLEARED"));

        assertThat(jdbc.queryForObject("select review_outcome from fraud_risk_score where id = ?", String.class, scoreId))
                .isEqualTo("CLEARED");
        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where event_type = 'FRAUD_FLAG_RAISED' and subject_id = ?",
                        Integer.class, determinationId))
                .as("clearing must not raise a second FRAUD_FLAG_RAISED -- only FRAUD_FLAG_REVIEWED")
                .isEqualTo(0);
    }

    private String robinKeycloakSubject() {
        return jdbc.queryForObject(
                "select keycloak_subject from worker where email = ?", String.class, "supervisor.robin@canopica.local");
    }

    private UUID determine(UUID programRequestId) {
        return determinations.determine(
                programRequestId, LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
    }
}
