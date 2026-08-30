package canopica.api.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import canopica.api.CaseFixtures;
import canopica.api.determination.DeterminationService;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The HTTP contract for the QC sample-trigger endpoint, and the role gate in front of it -- an internal,
 * Airflow-triggered operation, ADMIN-scoped the same "narrowest existing role" reasoning {@code /api/policy/**}
 * already takes ({@link PolicyParameterProposalControllerTest}'s own doc comment).
 */
class QcControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
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
}
