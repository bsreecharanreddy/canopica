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
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The HTTP contract for the QC sample-trigger endpoint (Task 4) and the human review queue (Task 5), and the
 * role gate in front of each -- {@code /api/internal/qc/**} an internal, Airflow-triggered operation,
 * ADMIN-scoped the same "narrowest existing role" reasoning {@code /api/policy/**} already takes ({@link
 * PolicyParameterProposalControllerTest}'s own doc comment); {@code /api/qc/**} a SUPERVISOR-scoped,
 * cross-caseload triage surface, same role and reasoning {@link FraudReviewControllerTest}'s own doc comment
 * gives for {@code /api/fraud/**}.
 */
class QcControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper objectMapper;
    @Autowired DeterminationService determinations;

    @Test
    void runSampleIsForbiddenForAWorker() throws Exception {
        mvc.perform(post("/api/internal/qc/run-sample")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void runSampleIsForbiddenForASupervisor() throws Exception {
        mvc.perform(post("/api/internal/qc/run-sample")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void runSampleWithAnExplicitSizeSamplesUpToThatManyEligibleDeterminations() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        determinations.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        mvc.perform(post("/api/internal/qc/run-sample?sampleSize=1")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sampled").value(1))
                .andExpect(jsonPath("$.flagged").value(0));

        assertThat(jdbc.queryForObject("select count(*) from payment_error_review", Integer.class))
                .isGreaterThanOrEqualTo(1);
    }

    @Test
    void reviewQueueIsForbiddenForAWorker() throws Exception {
        mvc.perform(get("/api/qc/review-queue").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void reviewQueueIsForbiddenForAnAdmin() throws Exception {
        mvc.perform(get("/api/qc/review-queue").header(HttpHeaders.AUTHORIZATION, "Bearer " + adminToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void reviewQueueOrdersUnreviewedDiscrepanciesLargestErrorFirstAndExcludesZeroDiffAndAlreadyReviewedRows()
            throws Exception {
        // Scoped to the ids this test itself created, not the queue's total size -- QcSamplingServiceTest
        // shares this same AbstractPostgresTest instance and deliberately leaves its own genuine,
        // permanently-unreviewed nonzero-diff rows behind (aDeterminationReproducedAgainstAMismatchedParameter
        // SetSurfacesARealDiff and its sibling), so an exact item-count assertion here would be a real,
        // order-dependent flake, not a hypothetical one -- the same shared-Postgres hazard AuditChainTest's
        // own doc comment already documents from the audit-log side.
        UUID smallErrorDetermination = determine(CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId());
        UUID largeErrorDetermination = determine(CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId());
        UUID zeroDiffDetermination = determine(CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId());
        UUID reviewedDetermination = determine(CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId());
        UUID smallErrorId = CaseFixtures.insertPaymentErrorReview(
                jdbc, smallErrorDetermination, new BigDecimal("649.00"), new BigDecimal("659.00"));
        UUID largeErrorId = CaseFixtures.insertPaymentErrorReview(
                jdbc, largeErrorDetermination, new BigDecimal("649.00"), new BigDecimal("749.00"));
        UUID zeroDiffId = CaseFixtures.insertPaymentErrorReview(
                jdbc, zeroDiffDetermination, new BigDecimal("649.00"), new BigDecimal("649.00"));
        UUID reviewedId = CaseFixtures.insertPaymentErrorReview(
                jdbc, reviewedDetermination, new BigDecimal("649.00"), new BigDecimal("729.00"));
        jdbc.update(
                "update payment_error_review set review_outcome = 'DISMISSED', reviewed_by = 'someone', "
                        + "reviewed_at = now() where id = ?",
                reviewedId);

        String response = mvc.perform(get("/api/qc/review-queue")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        List<String> ids = new ArrayList<>();
        objectMapper.readTree(response).forEach(item -> ids.add(item.get("id").asText()));

        assertThat(ids).doesNotContain(zeroDiffId.toString(), reviewedId.toString());
        assertThat(ids.indexOf(largeErrorId.toString()))
                .as("largest error first")
                .isLessThan(ids.indexOf(smallErrorId.toString()));
    }

    @Test
    void confirmSetsReviewOutcomeAppendsAnAuditEventAndNeverTouchesTheOriginalDetermination() throws Exception {
        UUID determinationId = determine(CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId());
        UUID reviewId = CaseFixtures.insertPaymentErrorReview(
                jdbc, determinationId, new BigDecimal("649.00"), new BigDecimal("749.00"));
        String originalBenefitAmount = jdbc.queryForObject(
                "select benefit_amount::text from eligibility_determination where id = ?", String.class, determinationId);

        mvc.perform(post("/api/qc/" + reviewId + "/confirm")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reviewOutcome").value("CONFIRMED_ERROR"))
                .andExpect(jsonPath("$.reviewedBy").value(robinKeycloakSubject()));

        assertThat(jdbc.queryForObject("select review_outcome from payment_error_review where id = ?", String.class, reviewId))
                .isEqualTo("CONFIRMED_ERROR");
        assertThat(jdbc.queryForObject(
                        "select benefit_amount::text from eligibility_determination where id = ?", String.class, determinationId))
                .as("confirming a QC discrepancy must never change the determination it flagged")
                .isEqualTo(originalBenefitAmount);
        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where event_type = 'QC_REVIEW_COMPLETED' and subject_id = ?",
                        Integer.class, determinationId))
                .isEqualTo(1);
    }

    @Test
    void dismissSetsReviewOutcomeAndDoesNotRaiseAnAdditionalFlagEvent() throws Exception {
        UUID determinationId = determine(CaseFixtures.threePersonWorkingHousehold(jdbc).programRequestId());
        UUID reviewId = CaseFixtures.insertPaymentErrorReview(
                jdbc, determinationId, new BigDecimal("649.00"), new BigDecimal("749.00"));

        mvc.perform(post("/api/qc/" + reviewId + "/dismiss")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reviewOutcome").value("DISMISSED"));

        assertThat(jdbc.queryForObject("select review_outcome from payment_error_review where id = ?", String.class, reviewId))
                .isEqualTo("DISMISSED");
        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where event_type = 'QC_DISCREPANCY_FLAGGED' and subject_id = ?",
                        Integer.class, determinationId))
                .as("dismissing must not raise a second QC_DISCREPANCY_FLAGGED -- only QC_REVIEW_COMPLETED")
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
