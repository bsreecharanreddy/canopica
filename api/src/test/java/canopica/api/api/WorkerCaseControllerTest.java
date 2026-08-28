package canopica.api.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.api.AbstractApiTest;
import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import canopica.api.determination.DeterminationService;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The Postgres container backing {@link AbstractPostgresTest} is a JVM-wide singleton, so the case list
 * this suite hits is never empty or exclusively this test's data -- every assertion below finds its own
 * fixture by id rather than assuming list length or position.
 *
 * <p>Caseload-scoped authorization (Task 2, design doc §2.1) is exercised here rather than in
 * {@code AuthorizationTest}, since it's a data-driven {@code case_assignment} check, not a role gate.
 */
class WorkerCaseControllerTest extends AbstractApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired DeterminationService determinationService;
    @Autowired ObjectMapper objectMapper;

    @Test
    void caseListReturnsOneRowPerProgramRequestWithHeadNameStatusAndLatestDetermination() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String response = mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode myCase = findByProgramRequestId(response, ids.programRequestId());
        assertThat(myCase).as("case list should include the program request just created").isNotNull();
        assertThat(myCase.get("householdHeadName").asText()).isEqualTo("Dana Reyes");
        assertThat(myCase.get("status").asText()).isEqualTo("SUBMITTED");
        assertThat(myCase.get("latestDetermination").get("eligible").asBoolean()).isTrue();
    }

    @Test
    void everyMoneyFieldCrossesTheWireAsAStringNotAJsonNumber() throws Exception {
        // types.ts has claimed `benefitAmount: string` since Phase 1a, and until this test it was simply
        // untrue: Jackson serialises BigDecimal as a JSON number by default, so the browser parsed it into a
        // double. The visible cost is cents: a $649.00 award renders as "$649/month", because JSON.parse
        // turns 649.00 into 649 and the trailing zeros are gone before any component sees them. The
        // invariant this repo states everywhere -- money never round-trips through a float -- was true of
        // the database, the rules engine and the DTOs, and false at exactly the last hop.
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String detail = mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String list = mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode fromDetail = objectMapper.readTree(detail).get("determinations").get(0).get("benefitAmount");
        JsonNode fromList = findByProgramRequestId(list, ids.programRequestId())
                .get("latestDetermination").get("benefitAmount");

        assertThat(fromDetail.isTextual()).as("determination benefitAmount as JSON string").isTrue();
        assertThat(fromList.isTextual()).as("case-list benefitAmount as JSON string").isTrue();
        // Scale preserved exactly as the database stored it -- the whole point of the string.
        assertThat(fromDetail.asText()).contains(".");
    }

    @Test
    void caseDetailReturnsDeterminationHistoryNewestFirstAndAppendsCaseViewedAudit() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID firstId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
        UUID secondId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 20), LocalDate.of(2025, 6, 1), "SYSTEM");

        mvc.perform(get("/api/program-requests/" + ids.programRequestId()).header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.determinations.length()").value(2))
                .andExpect(jsonPath("$.determinations[0].determinationId").value(secondId.toString()))
                .andExpect(jsonPath("$.determinations[1].determinationId").value(firstId.toString()));

        assertThat(jdbc.queryForObject(
                "select count(*) from audit_event where event_type = 'CASE_VIEWED' and subject_id = ?",
                Integer.class, ids.programRequestId())).isEqualTo(1);
    }

    @Test
    void traceEndpointReturnsTheSameDecisionNamesTheDmnModelDefines() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String response = mvc.perform(get("/api/determinations/" + determinationId + "/trace")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertThat(response).contains("Excess Shelter Deduction", "Net Income", "Benefit Amount");
        assertThat(response).contains("\"policyParameterVersion\":\"SNAP-FY2025\"");
    }

    @Test
    void workerViewingAnUnassignedHouseholdAutoClaimsItAndIsMarkedInAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk());

        UUID samWorkerId = provisionedWorkerId("worker.sam@canopica.local");
        assertThat(jdbc.queryForObject(
                "select worker_id from case_assignment where household_id = ?", UUID.class, ids.householdId()))
                .isEqualTo(samWorkerId);
        assertThat(jdbc.queryForObject(
                "select payload->>'in_assignment' from audit_event "
                        + "where event_type = 'CASE_VIEWED' and subject_id = ?",
                String.class, ids.programRequestId())).isEqualTo("true");
    }

    @Test
    void workerNotHoldingTheActiveAssignmentGets403() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), otherWorkerId);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void supervisorViewingAnUnassignedHouseholdIsAllowedButNotMarkedInAssignmentAndDoesNotClaimIt() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);

        mvc.perform(get("/api/program-requests/" + ids.programRequestId())
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + supervisorToken()))
                .andExpect(status().isOk());

        assertThat(jdbc.queryForObject(
                "select count(*) from case_assignment where household_id = ?", Integer.class, ids.householdId()))
                .as("a supervisor's view is an override, not a claim -- it must not create an assignment")
                .isEqualTo(0);
        assertThat(jdbc.queryForObject(
                "select payload->>'in_assignment' from audit_event "
                        + "where event_type = 'CASE_VIEWED' and subject_id = ?",
                String.class, ids.programRequestId())).isEqualTo("false");
    }

    @Test
    void auditTrailReturnsBothApplicationAndDeterminationEventsOrderedByOccurredAt() throws Exception {
        // CaseFixtures.threePersonWorkingHousehold bypasses IntakeService entirely (raw JDBC inserts), so it
        // never produces an APPLICATION_SUBMITTED audit event -- going through the real /api/applications
        // endpoint here instead, the same way IntakeControllerTest does, so this test exercises the real
        // path that actually writes that event, with a real HUMAN actor id.
        String submitResponse = mvc.perform(post("/api/applications")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + citizenToken())
                        .contentType(MediaType.APPLICATION_JSON).content(TestPayloads.threePersonWorkingHouseholdIntake()))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        UUID programRequestId = UUID.fromString(objectMapper.readTree(submitResponse).get("programRequestId").asText());

        // Unlike CaseFixtures.threePersonWorkingHousehold, the real /api/applications flow effective-dates
        // household composition from today (IntakeService uses the injected clock, not a fixed past date),
        // so determining "as of" a historical date like the other tests in this file use would see a
        // household of size 0 -- determine against today instead.
        LocalDate today = LocalDate.now();
        UUID determinationId = determinationService.determine(
                programRequestId, today, today.withDayOfMonth(1), "SYSTEM");

        String response = mvc.perform(get("/api/cases/" + programRequestId + "/audit")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode events = objectMapper.readTree(response);
        assertThat(events.isArray()).isTrue();

        JsonNode submitted = findByEventType(events, "APPLICATION_SUBMITTED");
        assertThat(submitted).as("audit trail should include the application-submitted event").isNotNull();
        assertThat(submitted.get("actorType").asText()).isEqualTo("HUMAN");

        JsonNode determined = findByEventType(events, "DETERMINATION_MADE");
        assertThat(determined).as("audit trail should include the determination-made event, keyed by its own subject id, not the program request's")
                .isNotNull();
        assertThat(determined.get("actorType").asText()).isEqualTo("SYSTEM");
        assertThat(determined.get("payload").get("benefitAmount").isTextual())
                .as("money inside the audit payload must still cross the wire as a string")
                .isTrue();

        // occurred_at is ordered ascending: submission happens before the determination it produces.
        long submittedIndex = indexOf(events, submitted);
        long determinedIndex = indexOf(events, determined);
        assertThat(submittedIndex).isLessThan(determinedIndex);

        // Sanity check the determination id really is the one just created, not a stray match.
        assertThat(determinationId).isNotNull();
    }

    @Test
    void auditTrailIsForbiddenForAWorkerNotHoldingTheActiveAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else Too", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), otherWorkerId);

        mvc.perform(get("/api/cases/" + ids.programRequestId() + "/audit")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditTrailCanReadBackADocumentClassifiedEventTheWorkerServiceWrites() throws Exception {
        // AuditEventType.DOCUMENT_CLASSIFIED is written by the Python worker's document_intake_consumer.py
        // via a raw insert, never by this module's own AuditService -- simulated here the same way, so this
        // test exercises the real risk: JdbcAuditService#findBySubject calls AuditEventType.valueOf(event_
        // type) on every row it reads, and would throw IllegalArgumentException on a row this enum doesn't
        // recognize. Confirms the wire response too: actorType derives from a literal "SYSTEM" string match
        // (AuditEventResponse.java), the same convention DETERMINATION_MADE's own "SYSTEM" actor already
        // established -- not a free-text worker-process identifier.
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID documentId = UUID.randomUUID();
        jdbc.update(
                "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
                        + "values ('DOCUMENT_CLASSIFIED', 'SYSTEM', 'program_request', ?, "
                        + "('{\"document_id\":\"' || ? || '\",\"document_type\":\"INCOME_REPORT\"}')::jsonb)",
                ids.programRequestId(), documentId.toString());

        String response = mvc.perform(get("/api/cases/" + ids.programRequestId() + "/audit")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode classified = findByEventType(objectMapper.readTree(response), "DOCUMENT_CLASSIFIED");
        assertThat(classified).as("the audit trail must be able to read back a worker-written event").isNotNull();
        assertThat(classified.get("actorType").asText()).isEqualTo("SYSTEM");
        assertThat(classified.get("payload").get("document_id").asText()).isEqualTo(documentId.toString());
    }

    @Test
    void dashboardStatsCountActiveAndPendingCasesScopedToThisWorkersOwnCaseload() throws Exception {
        // Triggers KeycloakWorkerSyncFilter's lazy provisioning of worker.sam's row before this test needs
        // its id -- same idiom workerViewingAnUnassignedHouseholdAutoClaimsItAndIsMarkedInAssignment uses.
        mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk());
        UUID samWorkerId = provisionedWorkerId("worker.sam@canopica.local");

        // The Postgres singleton this class's own doc comment describes means worker.sam may already hold
        // other assignments from earlier tests elsewhere in the full suite (any test that opens a case as
        // worker.sam auto-claims it) -- asserting an absolute count here would be exactly the "assumes list
        // length" anti-pattern that same doc comment warns against. Capture a baseline first and assert the
        // delta this test itself produces, the same way findByProgramRequestId finds its own fixture by id
        // rather than assuming position elsewhere in this file.
        JsonNode baseline = objectMapper.readTree(
                mvc.perform(get("/api/cases/dashboard").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                        .andExpect(status().isOk())
                        .andReturn().getResponse().getContentAsString());
        int baselineActive = baseline.get("activeCases").asInt();
        int baselinePending = baseline.get("pendingDetermination").asInt();

        var mine1 = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var mine2 = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var notMine = CaseFixtures.threePersonWorkingHousehold(jdbc);
        CaseFixtures.insertCaseAssignment(jdbc, mine1.householdId(), samWorkerId);
        CaseFixtures.insertCaseAssignment(jdbc, mine2.householdId(), samWorkerId);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Not Sam", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, notMine.householdId(), otherWorkerId);

        // mine1 gets a determination (no longer pending); mine2 and notMine do not.
        determinationService.determine(
                mine1.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        String response = mvc.perform(get("/api/cases/dashboard").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode json = objectMapper.readTree(response);
        assertThat(json.get("activeCases").asInt() - baselineActive)
                .as("only mine1 and mine2 are assigned to worker.sam -- notMine belongs to a different worker")
                .isEqualTo(2);
        assertThat(json.get("pendingDetermination").asInt() - baselinePending)
                .as("only mine2 has no determination yet")
                .isEqualTo(1);
    }

    private JsonNode findByEventType(JsonNode events, String eventType) {
        for (JsonNode node : events) {
            if (node.get("eventType").asText().equals(eventType)) {
                return node;
            }
        }
        return null;
    }

    private long indexOf(JsonNode events, JsonNode target) {
        long i = 0;
        for (JsonNode node : events) {
            if (node == target) {
                return i;
            }
            i++;
        }
        return -1;
    }

    private JsonNode findByProgramRequestId(String listResponse, UUID programRequestId) throws Exception {
        for (JsonNode node : objectMapper.readTree(listResponse)) {
            if (node.get("programRequestId").asText().equals(programRequestId.toString())) {
                return node;
            }
        }
        return null;
    }

    // KeycloakWorkerSyncFilter provisions the worker row lazily, on that user's first authenticated
    // request -- looking it up by the seeded realm user's own email (unique, stable) rather than decoding
    // the JWT's sub claim ourselves.
    private UUID provisionedWorkerId(String email) {
        return jdbc.queryForObject("select id from worker where email = ?", UUID.class, email);
    }
}
