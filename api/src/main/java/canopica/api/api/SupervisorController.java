package canopica.api.api;

import canopica.api.api.dto.ReassignCaseRequest;
import canopica.api.api.dto.SetSensitivityRequest;
import canopica.api.caseload.CaseAssignmentService;
import canopica.api.repo.HouseholdRepository;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * SUPERVISOR-only case management: explicit reassignment and sensitive-case flagging (design doc §2.1).
 * {@code SecurityConfig} restricts all of {@code /api/supervisor/**} to the SUPERVISOR role -- there is no
 * additional in-controller role check to duplicate.
 */
@RestController
@RequestMapping("/api/supervisor/households/{householdId}")
class SupervisorController {

    private final CaseAssignmentService caseAssignmentService;
    private final HouseholdRepository households;

    SupervisorController(CaseAssignmentService caseAssignmentService, HouseholdRepository households) {
        this.caseAssignmentService = caseAssignmentService;
        this.households = households;
    }

    @PostMapping("/reassign")
    ResponseEntity<Void> reassign(@PathVariable UUID householdId, @Valid @RequestBody ReassignCaseRequest request) {
        caseAssignmentService.reassign(householdId, request.workerId());
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/sensitivity")
    ResponseEntity<Void> setSensitivity(@PathVariable UUID householdId, @RequestBody SetSensitivityRequest request) {
        households.findById(householdId).orElseThrow();
        caseAssignmentService.flagSensitivity(householdId, request.isSensitive(), request.reason());
        return ResponseEntity.noContent().build();
    }
}
