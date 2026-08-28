package canopica.api.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.api.api.dto.AuditEventResponse;
import canopica.api.api.dto.CaseDetailResponse;
import canopica.api.api.dto.CaseloadStatsResponse;
import canopica.api.api.dto.CaseSummaryResponse;
import canopica.api.api.dto.DeterminationResponse;
import canopica.api.api.dto.TraceResponse;
import canopica.api.audit.AuditEventRecord;
import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import canopica.api.caseload.CaseAssignmentService;
import canopica.api.domain.Application;
import canopica.api.domain.DeterminationTrace;
import canopica.api.domain.EligibilityDetermination;
import canopica.api.domain.Household;
import canopica.api.domain.Person;
import canopica.api.domain.ProgramRequest;
import canopica.api.domain.Worker;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.DeterminationTraceRepository;
import canopica.api.repo.EligibilityDeterminationRepository;
import canopica.api.repo.HouseholdRepository;
import canopica.api.repo.PersonRepository;
import canopica.api.repo.ProgramRequestRepository;
import canopica.api.repo.WorkerRepository;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
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
    private final CaseAssignmentService caseAssignmentService;
    private final AuditService auditService;
    private final ObjectMapper objectMapper;
    private final WorkerRepository workers;
    private final Clock clock;

    WorkerCaseController(JdbcTemplate jdbc, ProgramRequestRepository programRequests,
            ApplicationRepository applications, HouseholdRepository households, PersonRepository persons,
            EligibilityDeterminationRepository determinations, DeterminationTraceRepository traces,
            CaseAssignmentService caseAssignmentService, AuditService auditService, ObjectMapper objectMapper,
            WorkerRepository workers, Clock clock) {
        this.jdbc = jdbc;
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.persons = persons;
        this.determinations = determinations;
        this.traces = traces;
        this.caseAssignmentService = caseAssignmentService;
        this.auditService = auditService;
        this.objectMapper = objectMapper;
        this.workers = workers;
        this.clock = clock;
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

        boolean inAssignment = caseAssignmentService.checkCaseloadAccess(household.getId(), authentication);

        List<DeterminationResponse> history = determinations.findByProgramRequestIdOrderByDecidedAtDesc(id)
                .stream().map(DeterminationResponse::from).toList();

        auditService.append(AuditEventType.CASE_VIEWED, authentication.getName(), "program_request", id,
                Map.of("in_assignment", inAssignment));

        return new CaseDetailResponse(id, application.getId(), household.getId(),
                head.getFirstName() + " " + head.getLastName(), programRequest.getProgramCode(),
                programRequest.getStatus(), programRequest.getRequestedOn(), history);
    }

    /**
     * A case's full audit story, oldest first. No single {@code audit_event} subject owns every event a
     * case produces -- {@code APPLICATION_SUBMITTED}/{@code CASE_VIEWED} are keyed on the program request
     * itself, but each {@code DETERMINATION_MADE} is keyed on its own determination id -- so this composes
     * one {@link AuditService#findBySubject} call per subject and merges by {@code occurredAt}. Does not
     * itself write a {@code CASE_VIEWED} event: {@link #caseDetail} already does, on the same page load
     * that fetches this.
     */
    @GetMapping("/api/cases/{programRequestId}/audit")
    List<AuditEventResponse> auditTrail(@PathVariable UUID programRequestId, Authentication authentication) {
        ProgramRequest programRequest = programRequests.findById(programRequestId).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        Household household = households.findById(application.getHouseholdId()).orElseThrow();
        caseAssignmentService.checkCaseloadAccess(household.getId(), authentication);

        return eventsForCase(programRequestId).stream().map(AuditEventResponse::from).toList();
    }

    /** Shared by {@link #auditTrail} and {@link #dashboard} -- see {@link #auditTrail}'s own doc for why this can't be one subject lookup. */
    private List<AuditEventRecord> eventsForCase(UUID programRequestId) {
        List<AuditEventRecord> events =
                new ArrayList<>(auditService.findBySubject("program_request", programRequestId));
        for (EligibilityDetermination determination :
                determinations.findByProgramRequestIdOrderByDecidedAtDesc(programRequestId)) {
            events.addAll(auditService.findBySubject("eligibility_determination", determination.getId()));
        }
        events.sort(Comparator.comparing(AuditEventRecord::occurredAt));
        return events;
    }

    /**
     * Real case counts for the signed-in worker's own caseload -- not {@link #listCases}'s roster, which
     * applies no caseload filter at all today (see {@link ProgramRequestRepository#findByAssignedWorker}'s
     * own doc). {@code activeCases} excludes only {@code WITHDRAWN}: {@code status} has no code path that
     * ever sets it to anything but {@code SUBMITTED} at creation today (verified live -- {@code
     * IntakeService} is the only writer, {@code ProgramRequest} has no mutator), so this is the schema's
     * real intent, not today's behavior; every real row currently counts as active. {@code
     * pendingDetermination} counts cases with no {@link EligibilityDetermination} row yet, which does not
     * depend on that gap.
     */
    @GetMapping("/api/cases/dashboard")
    CaseloadStatsResponse dashboard(Authentication authentication) {
        Worker viewer = workers.findByKeycloakSubject(authentication.getName())
                .orElseThrow(() -> new NoSuchElementException("no worker row for " + authentication.getName()));
        List<ProgramRequest> caseload =
                programRequests.findByAssignedWorker(viewer.getId(), LocalDate.now(clock));

        int activeCases = 0;
        int pendingDetermination = 0;
        List<AuditEventRecord> recentEvents = new ArrayList<>();
        for (ProgramRequest programRequest : caseload) {
            if (!"WITHDRAWN".equals(programRequest.getStatus())) {
                activeCases++;
            }
            if (determinations.findByProgramRequestIdOrderByDecidedAtDesc(programRequest.getId()).isEmpty()) {
                pendingDetermination++;
            }
            recentEvents.addAll(eventsForCase(programRequest.getId()));
        }
        recentEvents.sort(Comparator.comparing(AuditEventRecord::occurredAt).reversed());

        List<AuditEventResponse> recent =
                recentEvents.stream().limit(10).map(AuditEventResponse::from).toList();
        return new CaseloadStatsResponse(activeCases, pendingDetermination, recent);
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
