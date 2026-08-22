package ies.portal.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import ies.portal.AbstractApiTest;
import ies.portal.AbstractPostgresTest;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The Postgres container backing {@link AbstractPostgresTest} is a JVM-wide singleton shared with every
 * other test class, so assertions below check the row this test's own submission created (by id), never
 * an absolute count across the whole {@code program_request}/{@code audit_event} tables.
 */
class IntakeControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void submittingAnApplicationCreatesAProgramRequestAndAnAuditEvent() throws Exception {
        String body = TestPayloads.threePersonWorkingHouseholdIntake();

        String response = mvc.perform(post("/api/applications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.programRequestId").isNotEmpty())
                .andReturn().getResponse().getContentAsString();

        UUID programRequestId = UUID.fromString(objectMapper.readTree(response).get("programRequestId").asText());

        assertThat(jdbc.queryForObject(
                "select count(*) from program_request where id = ? and program_code = 'SNAP'",
                Integer.class, programRequestId)).isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select count(*) from audit_event where event_type = 'APPLICATION_SUBMITTED' and subject_id = ?",
                Integer.class, programRequestId)).isEqualTo(1);
    }

    @Test
    void submittingAnApplicationCreatesExactlyOneOutstandingIncomeVerification() throws Exception {
        String body = TestPayloads.threePersonWorkingHouseholdIntake();

        String response = mvc.perform(post("/api/applications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        UUID programRequestId = UUID.fromString(objectMapper.readTree(response).get("programRequestId").asText());

        assertThat(jdbc.queryForObject(
                "select count(*) from verification where program_request_id = ? "
                        + "and data_element = 'INCOME' and status = 'OUTSTANDING'",
                Integer.class, programRequestId)).isEqualTo(1);
    }

    @Test
    void rejectsAnIntakeWithNoHouseholdMembers() throws Exception {
        mvc.perform(post("/api/applications").header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(TestPayloads.intakeWithNoMembers()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("members"));
    }

    @Test
    void rejectsAnIntakeWhoseEffectiveDatesAreInverted() throws Exception {
        mvc.perform(post("/api/applications").header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(TestPayloads.intakeWithInvertedIncomeDates()))
                .andExpect(status().isBadRequest());
    }
}
