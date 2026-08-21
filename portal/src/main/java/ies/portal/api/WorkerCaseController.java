package ies.portal.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import ies.portal.api.dto.CaseDetailResponse;
import ies.portal.api.dto.CaseSummaryResponse;
import ies.portal.api.dto.DeterminationResponse;
import ies.portal.api.dto.TraceResponse;
import ies.portal.audit.AuditEventType;
import ies.portal.audit.AuditService;
import ies.portal.domain.Application;
import ies.portal.domain.DeterminationTrace;
import ies.portal.domain.EligibilityDetermination;
import ies.portal.domain.Household;
import ies.portal.domain.Person;
import ies.portal.domain.ProgramRequest;
import ies.portal.repo.ApplicationRepository;
import ies.portal.repo.DeterminationTraceRepository;
import ies.portal.repo.EligibilityDeterminationRepository;
import ies.portal.repo.HouseholdRepository;
import ies.portal.repo.PersonRepository;
import ies.portal.repo.ProgramRequestRepository;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/**
 * The worker-facing read views over a case: the caseload roster, one case's full detail (including its
 * append-only determination history), and one determination's DMN trace. Writing a new determination is
 * {@link DeterminationController}; this controller is read-only except for the {@code CASE_VIEWED} audit
 * event opening a case's detail generates -- the row-level-access evidence Phase 1b's {@code
 * mart_access_review} reports on.
 */
@RestController
class WorkerCaseController {

    private final JdbcTemplate jdbc;
    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final HouseholdRepository households;
    private final PersonRepository persons;
    private final EligibilityDeterminationRepository determinations;
    private final DeterminationTraceRepository traces;
    private final AuditService auditService;
    private final ObjectMapper objectMapper;

    WorkerCaseController(JdbcTemplate jdbc, ProgramRequestRepository programRequests,
            ApplicationRepository applications, HouseholdRepository households, PersonRepository persons,
            EligibilityDeterminationRepository determinations, DeterminationTraceRepository traces,
            AuditService auditService, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.persons = persons;
        this.determinations = determinations;
        this.traces = traces;
        this.auditService = auditService;
        this.objectMapper = objectMapper;
    }

    @GetMapping("/api/worker/cases")
    List<CaseSummaryResponse> listCases() {
        return jdbc.query(
                """
                select pr.id as program_request_id, pr.status, a.submitted_at,
                       p.first_name || ' ' || p.last_name as household_head_name,
                       latest.eligible as latest_eligible, latest.benefit_amount as latest_benefit_amount,
                       latest.decided_at as latest_decided_at
                from program_request pr
                join application a on a.id = pr.application_id
                join household h on h.id = a.household_id
                join person p on p.id = h.head_person_id
                left join lateral (
                    select ed.eligible, ed.benefit_amount, ed.decided_at
                    from eligibility_determination ed
                    where ed.program_request_id = pr.id
                    order by ed.decided_at desc
                    limit 1
                ) latest on true
                order by a.submitted_at desc
                """,
                (rs, rowNum) -> new CaseSummaryResponse(
                        (UUID) rs.getObject("program_request_id"),
                        rs.getString("household_head_name"),
                        rs.getString("status"),
                        rs.getTimestamp("submitted_at").toInstant(),
                        rs.getTimestamp("latest_decided_at") == null ? null
                                : new CaseSummaryResponse.LatestDetermination(
                                        rs.getBoolean("latest_eligible"),
                                        rs.getBigDecimal("latest_benefit_amount"),
                                        rs.getTimestamp("latest_decided_at").toInstant())));
    }

    @GetMapping("/api/program-requests/{id}")
    CaseDetailResponse caseDetail(@PathVariable UUID id, Authentication authentication) {
        ProgramRequest programRequest = programRequests.findById(id).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        Household household = households.findById(application.getHouseholdId()).orElseThrow();
        Person head = persons.findById(household.getHeadPersonId()).orElseThrow();
        List<DeterminationResponse> history = determinations.findByProgramRequestIdOrderByDecidedAtDesc(id)
                .stream().map(DeterminationResponse::from).toList();

        auditService.append(AuditEventType.CASE_VIEWED, authentication.getName(), "program_request", id, Map.of());

        return new CaseDetailResponse(id, application.getId(), household.getId(),
                head.getFirstName() + " " + head.getLastName(), programRequest.getProgramCode(),
                programRequest.getStatus(), programRequest.getRequestedOn(), history);
    }

    @GetMapping("/api/determinations/{id}/trace")
    TraceResponse trace(@PathVariable UUID id) {
        DeterminationTrace trace = traces.findByDeterminationId(id).orElseThrow();
        EligibilityDetermination determination = determinations.findById(id).orElseThrow();
        return new TraceResponse(readJson(trace.getInputSnapshot()), readJson(trace.getDecisionResults()),
                trace.getDmnModelHash(), determination.getPolicyParameterVersion());
    }

    private JsonNode readJson(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to parse stored trace JSON", e);
        }
    }
}
