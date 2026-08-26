package canopica.api.verification;

import canopica.api.api.dto.VerificationStatusResponse;
import canopica.api.caseload.CaseAssignmentService;
import canopica.api.domain.Application;
import canopica.api.domain.ProgramRequest;
import canopica.api.domain.Verification;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.ProgramRequestRepository;
import canopica.api.repo.VerificationRepository;
import canopica.api.repo.VerificationResponseRepository;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The mocked external verification interface's worker-facing surface (design doc §2.2): request/resolve
 * one outstanding verification and read current status. Gated by the exact same caseload check
 * {@link CaseAssignmentService} enforces for case viewing (Task 2) -- a WORKER without the active
 * assignment on this household gets 403 here too, and a SUPERVISOR always gets in.
 */
@RestController
@RequestMapping("/api/program-requests/{programRequestId}/verifications")
class VerificationController {

    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final VerificationRepository verifications;
    private final VerificationResponseRepository verificationResponses;
    private final CaseAssignmentService caseAssignmentService;
    private final MockVerificationService mockVerificationService;

    VerificationController(ProgramRequestRepository programRequests, ApplicationRepository applications,
            VerificationRepository verifications, VerificationResponseRepository verificationResponses,
            CaseAssignmentService caseAssignmentService, MockVerificationService mockVerificationService) {
        this.programRequests = programRequests;
        this.applications = applications;
        this.verifications = verifications;
        this.verificationResponses = verificationResponses;
        this.caseAssignmentService = caseAssignmentService;
        this.mockVerificationService = mockVerificationService;
    }

    @GetMapping
    List<VerificationStatusResponse> list(@PathVariable UUID programRequestId, Authentication authentication) {
        caseAssignmentService.checkCaseloadAccess(householdIdFor(programRequestId), authentication);

        return verifications.findByProgramRequestId(programRequestId).stream()
                .map(v -> VerificationStatusResponse.from(
                        v, verificationResponses.findByVerificationId(v.getId()).orElse(null)))
                .toList();
    }

    @PostMapping("/{verificationId}/request")
    VerificationStatusResponse request(@PathVariable UUID programRequestId, @PathVariable UUID verificationId,
            Authentication authentication) {
        caseAssignmentService.checkCaseloadAccess(householdIdFor(programRequestId), authentication);

        // Confirms verificationId genuinely belongs to programRequestId before acting on it -- without
        // this, a worker holding assignment on household A could supply a verificationId that actually
        // belongs to household B and act on it, bypassing the assignment check above entirely.
        Verification verification = verifications.findByProgramRequestId(programRequestId).stream()
                .filter(v -> v.getId().equals(verificationId))
                .findFirst()
                .orElseThrow(() -> new NoSuchElementException(
                        "no verification " + verificationId + " for program request " + programRequestId));

        mockVerificationService.requestVerification(verification.getId(), authentication.getName());

        Verification resolved = verifications.findById(verificationId).orElseThrow();
        var response = verificationResponses.findByVerificationId(verificationId).orElseThrow();
        return VerificationStatusResponse.from(resolved, response);
    }

    private UUID householdIdFor(UUID programRequestId) {
        ProgramRequest programRequest = programRequests.findById(programRequestId).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        return application.getHouseholdId();
    }
}
