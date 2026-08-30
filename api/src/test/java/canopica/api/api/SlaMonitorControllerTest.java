package canopica.api.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The role gate in front of the Case SLA/Compliance Monitor's at-risk queue -- SUPERVISOR-scoped, same
 * cross-caseload triage-queue reasoning {@code /api/fraud/**}/{@code /api/qc/**} already document. The
 * query's own correctness (aging, ordering, stall-reason surfacing) is {@link
 * canopica.api.caseload.AtRiskCaseQueryTest}'s job, not this class's.
 */
class SlaMonitorControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;

    @Test
    void atRiskQueueIsForbiddenForAWorker() throws Exception {
        mvc.perform(get("/api/sla/at-risk-queue").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void atRiskQueueIsOkForASupervisor() throws Exception {
        mvc.perform(get("/api/sla/at-risk-queue").header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk());
    }
}
