package canopica.portal.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.portal.AbstractPostgresTest;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

class AuthorizationTest extends AbstractPostgresTest {

    @Autowired MockMvc mvc;

    @Test
    void customerRoleIsForbiddenFromTheWorkerCaseList() throws Exception {
        mvc.perform(get("/api/worker/cases").header("X-Canopica-Role", "CUSTOMER"))
                .andExpect(status().isForbidden());
    }

    @Test
    void customerRoleIsForbiddenFromCreatingADetermination() throws Exception {
        mvc.perform(post("/api/program-requests/" + UUID.randomUUID() + "/determinations")
                        .header("X-Canopica-Role", "CUSTOMER")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"asOfDate\":\"2025-06-15\",\"benefitMonth\":\"2025-06-01\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingRoleHeaderIsUnauthorized() throws Exception {
        mvc.perform(get("/api/worker/cases")).andExpect(status().isUnauthorized());
    }

    @Test
    void unrecognizedRoleHeaderIsUnauthorized() throws Exception {
        mvc.perform(get("/api/worker/cases").header("X-Canopica-Role", "ADMIN"))
                .andExpect(status().isUnauthorized());
    }
}
