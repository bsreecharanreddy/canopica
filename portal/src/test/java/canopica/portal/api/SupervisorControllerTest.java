package canopica.portal.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.portal.AbstractApiTest;
import canopica.portal.CaseFixtures;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/** SUPERVISOR-only reassignment and sensitivity-flag endpoints (Task 2, design doc §2.1). */
class SupervisorControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    @Test
    void reassignReplacesTheActiveAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID originalWorkerId = CaseFixtures.insertWorker(jdbc, "Original Worker", "WORKER");
        UUID newWorkerId = CaseFixtures.insertWorker(jdbc, "New Worker", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), originalWorkerId);

        mvc.perform(post("/api/supervisor/households/" + ids.householdId() + "/reassign")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"workerId\":\"" + newWorkerId + "\"}"))
                .andExpect(status().isNoContent());

        // The still-open (effective_to is null) row is the new assignment; the original row is left in
        // place with its effective_to closed out, not deleted -- the exact end-dating mechanics are
        // covered in detail by CaseAssignmentServiceTest, so this only checks what the HTTP layer adds:
        // that the endpoint actually reaches the service and the caseload query sees the new owner.
        assertThat(jdbc.queryForObject(
                        "select worker_id from case_assignment where household_id = ? and effective_to is null",
                        UUID.class, ids.householdId()))
                .isEqualTo(newWorkerId);
        assertThat(jdbc.queryForObject(
                        "select count(*) from case_assignment where household_id = ?", Integer.class, ids.householdId()))
                .isEqualTo(2);
    }

    @Test
    void sensitivityUpdateSetsIsSensitiveAndReason() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        mvc.perform(put("/api/supervisor/households/" + ids.householdId() + "/sensitivity")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isSensitive\":true,\"reason\":\"possible identity theft\"}"))
                .andExpect(status().isNoContent());

        var row = jdbc.queryForMap("select is_sensitive, sensitive_reason from household where id = ?", ids.householdId());
        assertThat(row.get("is_sensitive")).isEqualTo(true);
        assertThat(row.get("sensitive_reason")).isEqualTo("possible identity theft");
    }

    @Test
    void workerTokenIsForbiddenFromReassigning() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID newWorkerId = CaseFixtures.insertWorker(jdbc, "New Worker", "WORKER");

        mvc.perform(post("/api/supervisor/households/" + ids.householdId() + "/reassign")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"workerId\":\"" + newWorkerId + "\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void workerTokenIsForbiddenFromSettingSensitivity() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        mvc.perform(put("/api/supervisor/households/" + ids.householdId() + "/sensitivity")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"isSensitive\":true,\"reason\":\"possible identity theft\"}"))
                .andExpect(status().isForbidden());
    }
}
