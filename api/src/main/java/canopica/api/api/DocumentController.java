package canopica.api.api;

import canopica.api.api.dto.ConfirmDocumentRequest;
import canopica.api.api.dto.DocumentResponse;
import canopica.api.api.dto.DocumentReviewItemResponse;
import canopica.api.caseload.CaseAssignmentService;
import canopica.api.document.Document;
import canopica.api.document.DocumentService;
import canopica.api.domain.Application;
import canopica.api.domain.Household;
import canopica.api.domain.Person;
import canopica.api.domain.ProgramRequest;
import canopica.api.domain.Worker;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.DocumentRepository;
import canopica.api.repo.HouseholdRepository;
import canopica.api.repo.PersonRepository;
import canopica.api.repo.ProgramRequestRepository;
import canopica.api.repo.WorkerRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import java.time.Clock;
import java.time.LocalDate;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * Document upload (Phase 3 Task 2), review queue and confirm (Task 4). Worker-authenticated only, a real
 * narrowing from the implementation plan's own "worker- or citizen-authenticated" language: {@link
 * canopica.api.config.SecurityConfig}'s two filter chains are realm-specific and mutually exclusive by
 * path, so one endpoint cannot actually accept either token type without a materially bigger security-
 * config change (a multi-issuer decoder) this task doesn't need -- a caseworker uploading/reviewing on a
 * case's behalf matches this project's already-narrow citizen self-service surface (three read/write paths
 * total, none of them uploads) more than it contradicts it. Citizen self-upload is real future scope, not
 * silently dropped -- revisit if a real need for it emerges.
 */
@RestController
class DocumentController {

    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final HouseholdRepository households;
    private final PersonRepository persons;
    private final DocumentRepository documents;
    private final WorkerRepository workers;
    private final CaseAssignmentService caseAssignmentService;
    private final DocumentService documentService;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    DocumentController(
            ProgramRequestRepository programRequests,
            ApplicationRepository applications,
            HouseholdRepository households,
            PersonRepository persons,
            DocumentRepository documents,
            WorkerRepository workers,
            CaseAssignmentService caseAssignmentService,
            DocumentService documentService,
            ObjectMapper objectMapper,
            Clock clock) {
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.persons = persons;
        this.documents = documents;
        this.workers = workers;
        this.caseAssignmentService = caseAssignmentService;
        this.documentService = documentService;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @PostMapping("/api/cases/{programRequestId}/documents")
    DocumentResponse upload(
            @PathVariable UUID programRequestId,
            @RequestParam("file") MultipartFile file,
            Authentication authentication) {
        Household household = householdFor(programRequestId);
        caseAssignmentService.checkCaseloadAccess(household.getId(), authentication);

        Document document = documentService.upload(programRequestId, file, authentication.getName());
        return DocumentResponse.from(document);
    }

    /**
     * Every {@code CLASSIFIED} document across the signed-in worker's own caseload, lowest confidence
     * first (design doc §2.3's "confidence drives prioritization") -- same {@code findByAssignedWorker}
     * caseload-scoping {@link WorkerCaseController#dashboard} already uses, not {@link
     * CaseAssignmentService#checkCaseloadAccess}'s single-household check, since this lists across an
     * entire caseload rather than acting on one case.
     */
    @GetMapping("/api/cases/documents/review-queue")
    List<DocumentReviewItemResponse> reviewQueue(Authentication authentication) {
        Worker viewer = workers.findByKeycloakSubject(authentication.getName())
                .orElseThrow(() -> new NoSuchElementException("no worker row for " + authentication.getName()));
        List<UUID> caseloadProgramRequestIds = programRequests.findByAssignedWorker(viewer.getId(), LocalDate.now(clock))
                .stream().map(ProgramRequest::getId).toList();
        if (caseloadProgramRequestIds.isEmpty()) {
            return List.of();
        }

        return documents
                .findByProgramRequestIdInAndClassificationStatusOrderByExtractionConfidenceAsc(
                        caseloadProgramRequestIds, "CLASSIFIED")
                .stream()
                .map(this::toReviewItem)
                .toList();
    }

    // householdHeadName/headPersonId ride along on every review-queue row so the review UI can pre-fill an
    // income record's personId without a second round trip -- SNAP income reporting is overwhelmingly about
    // the head of household; a full member picker is real future scope this task doesn't need yet.
    private DocumentReviewItemResponse toReviewItem(Document document) {
        Household household = householdFor(document.getProgramRequestId());
        Person head = persons.findById(household.getHeadPersonId()).orElseThrow();
        return DocumentReviewItemResponse.from(document, readExtraction(document), head.getId(),
                head.getFirstName() + " " + head.getLastName());
    }

    /**
     * The literal human-confirmation gate design doc §2.3 requires with no bypass: the worker's final,
     * edited-or-accepted field values -- never the raw extraction -- are what {@link DocumentService
     * #confirm} actually applies.
     */
    @PostMapping("/api/cases/documents/{documentId}/confirm")
    DocumentResponse confirm(
            @PathVariable UUID documentId, @Valid @RequestBody ConfirmDocumentRequest request,
            Authentication authentication) {
        Document document = documents.findById(documentId)
                .orElseThrow(() -> new NoSuchElementException("no document with id " + documentId));
        Household household = householdFor(document.getProgramRequestId());
        caseAssignmentService.checkCaseloadAccess(household.getId(), authentication);

        List<DocumentService.ConfirmedIncome> incomeRecords = request.incomeRecords().stream()
                .map(entry -> new DocumentService.ConfirmedIncome(entry.personId(), entry.incomeType(),
                        entry.earned(), entry.monthlyAmount(), entry.effectiveFrom(), entry.effectiveTo()))
                .toList();

        Document confirmed = documentService.confirm(
                documentId, request.satisfiedVerificationIds(), incomeRecords, household.getHeadPersonId(),
                authentication.getName());
        return DocumentResponse.from(confirmed);
    }

    private Household householdFor(UUID programRequestId) {
        ProgramRequest programRequest = programRequests.findById(programRequestId).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        return households.findById(application.getHouseholdId()).orElseThrow();
    }

    private JsonNode readExtraction(Document document) {
        if (document.getExtraction() == null) {
            return objectMapper.nullNode();
        }
        try {
            return objectMapper.readTree(document.getExtraction());
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to parse stored extraction JSON for document " + document.getId(), e);
        }
    }
}
