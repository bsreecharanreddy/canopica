package canopica.api.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.api.api.dto.MyProgramRequestResponse;
import canopica.api.api.dto.TraceResponse;
import canopica.api.config.KeycloakCitizenLinkFilter;
import canopica.api.domain.Application;
import canopica.api.domain.DeterminationTrace;
import canopica.api.domain.EligibilityDetermination;
import canopica.api.domain.Household;
import canopica.api.domain.ProgramRequest;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.DeterminationTraceRepository;
import canopica.api.repo.EligibilityDeterminationRepository;
import canopica.api.repo.HouseholdRepository;
import canopica.api.repo.ProgramRequestRepository;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The citizen-facing read views over a caller's own data: their own program requests, and one of their own
 * determinations' DMN trace -- the "why was I denied" path Task 2's Policy Q&A feature calls server-side.
 * Ownership, not caseload assignment: ownership is resolved by {@link KeycloakCitizenLinkFilter} from the
 * caller's own JWT, not from a role or an assignment table -- a citizen owns whatever household(s) trace
 * back to a person row carrying their subject as its head, never anyone else's.
 */
@RestController
@RequestMapping("/api/my")
class CitizenController {

    private final JdbcTemplate jdbc;
    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final HouseholdRepository households;
    private final EligibilityDeterminationRepository determinations;
    private final DeterminationTraceRepository traces;
    private final ObjectMapper objectMapper;

    CitizenController(JdbcTemplate jdbc, ProgramRequestRepository programRequests,
            ApplicationRepository applications, HouseholdRepository households,
            EligibilityDeterminationRepository determinations, DeterminationTraceRepository traces,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.determinations = determinations;
        this.traces = traces;
        this.objectMapper = objectMapper;
    }

    @GetMapping("/program-requests")
    List<MyProgramRequestResponse> myProgramRequests(HttpServletRequest request) {
        List<UUID> personIds = ownedPersonIds(request);
        if (personIds.isEmpty()) {
            return List.of();
        }
        return jdbc.query(
                """
                select pr.id as program_request_id, pr.program_code, pr.status, a.submitted_at
                from program_request pr
                join application a on a.id = pr.application_id
                join household h on h.id = a.household_id
                where h.head_person_id = any(?)
                order by a.submitted_at desc
                """,
                ps -> ps.setArray(1, ps.getConnection().createArrayOf("uuid", personIds.toArray())),
                (rs, rowNum) -> new MyProgramRequestResponse(
                        (UUID) rs.getObject("program_request_id"),
                        rs.getString("program_code"),
                        rs.getString("status"),
                        rs.getTimestamp("submitted_at").toInstant()));
    }

    @GetMapping("/determinations/{id}/trace")
    TraceResponse trace(@PathVariable UUID id, HttpServletRequest request) {
        List<UUID> personIds = ownedPersonIds(request);

        EligibilityDetermination determination = determinations.findById(id).orElseThrow();
        ProgramRequest programRequest = programRequests.findById(determination.getProgramRequestId()).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        Household household = households.findById(application.getHouseholdId()).orElseThrow();

        if (!personIds.contains(household.getHeadPersonId())) {
            throw new AccessDeniedException("determination " + id + " does not belong to the caller");
        }

        DeterminationTrace trace = traces.findByDeterminationId(id).orElseThrow();
        return new TraceResponse(readJson(trace.getInputSnapshot()), readJson(trace.getDecisionResults()),
                trace.getDmnModelHash(), determination.getPolicyParameterVersion());
    }

    @SuppressWarnings("unchecked")
    private static List<UUID> ownedPersonIds(HttpServletRequest request) {
        List<UUID> personIds = (List<UUID>) request.getAttribute(KeycloakCitizenLinkFilter.PERSON_IDS_ATTRIBUTE);
        return personIds == null ? List.of() : personIds;
    }

    private JsonNode readJson(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to parse stored trace JSON", e);
        }
    }
}
