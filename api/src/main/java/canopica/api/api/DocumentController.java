package canopica.api.api;

import canopica.api.api.dto.DocumentResponse;
import canopica.api.caseload.CaseAssignmentService;
import canopica.api.document.Document;
import canopica.api.document.DocumentService;
import canopica.api.domain.Application;
import canopica.api.domain.Household;
import canopica.api.domain.ProgramRequest;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.HouseholdRepository;
import canopica.api.repo.ProgramRequestRepository;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * Document upload (Phase 3 Task 2). Worker-authenticated only, a real narrowing from the implementation
 * plan's own "worker- or citizen-authenticated" language: {@link canopica.api.config.SecurityConfig}'s two
 * filter chains are realm-specific and mutually exclusive by path, so one endpoint cannot actually accept
 * either token type without a materially bigger security-config change (a multi-issuer decoder) this task
 * doesn't need -- a caseworker uploading on a case's behalf matches this project's already-narrow citizen
 * self-service surface (three read/write paths total, none of them uploads) more than it contradicts it.
 * Citizen self-upload is real future scope, not silently dropped -- revisit if a real need for it emerges.
 */
@RestController
class DocumentController {

    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final HouseholdRepository households;
    private final CaseAssignmentService caseAssignmentService;
    private final DocumentService documentService;

    DocumentController(
            ProgramRequestRepository programRequests,
            ApplicationRepository applications,
            HouseholdRepository households,
            CaseAssignmentService caseAssignmentService,
            DocumentService documentService) {
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.caseAssignmentService = caseAssignmentService;
        this.documentService = documentService;
    }

    @PostMapping("/api/cases/{programRequestId}/documents")
    DocumentResponse upload(
            @PathVariable UUID programRequestId,
            @RequestParam("file") MultipartFile file,
            Authentication authentication) {
        ProgramRequest programRequest = programRequests.findById(programRequestId).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        Household household = households.findById(application.getHouseholdId()).orElseThrow();
        caseAssignmentService.checkCaseloadAccess(household.getId(), authentication);

        Document document = documentService.upload(programRequestId, file, authentication.getName());
        return DocumentResponse.from(document);
    }
}
