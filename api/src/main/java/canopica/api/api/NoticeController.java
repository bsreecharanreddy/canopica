package canopica.api.api;

import canopica.api.api.dto.NoticeReviewItemResponse;
import canopica.api.api.dto.NoticeResponse;
import canopica.api.caseload.CaseAssignmentService;
import canopica.api.domain.Application;
import canopica.api.domain.Household;
import canopica.api.domain.ProgramRequest;
import canopica.api.domain.Worker;
import canopica.api.notice.Notice;
import canopica.api.notice.NoticeService;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.HouseholdRepository;
import canopica.api.repo.NoticeRepository;
import canopica.api.repo.ProgramRequestRepository;
import canopica.api.repo.WorkerRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.LocalDate;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Notice review queue, approve, and reject (Phase 3 Task 6). Worker-authenticated only, same narrowing
 * {@link DocumentController}'s own doc comment already justifies for this realm's security-config shape.
 */
@RestController
class NoticeController {

    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final HouseholdRepository households;
    private final WorkerRepository workers;
    private final NoticeRepository notices;
    private final CaseAssignmentService caseAssignmentService;
    private final NoticeService noticeService;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    NoticeController(
            ProgramRequestRepository programRequests,
            ApplicationRepository applications,
            HouseholdRepository households,
            WorkerRepository workers,
            NoticeRepository notices,
            CaseAssignmentService caseAssignmentService,
            NoticeService noticeService,
            ObjectMapper objectMapper,
            Clock clock) {
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.workers = workers;
        this.notices = notices;
        this.caseAssignmentService = caseAssignmentService;
        this.noticeService = noticeService;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    /**
     * Every DRAFT notice across the signed-in worker's own caseload, oldest first ({@code
     * notice_review_queue_idx}, V20) -- same {@code findByAssignedWorker} caseload-scoping {@link
     * DocumentController#reviewQueue} already uses.
     */
    @GetMapping("/api/cases/notices/review-queue")
    List<NoticeReviewItemResponse> reviewQueue(Authentication authentication) {
        Worker viewer = workers.findByKeycloakSubject(authentication.getName())
                .orElseThrow(() -> new NoSuchElementException("no worker row for " + authentication.getName()));
        List<UUID> caseloadProgramRequestIds = programRequests.findByAssignedWorker(viewer.getId(), LocalDate.now(clock))
                .stream().map(ProgramRequest::getId).toList();
        if (caseloadProgramRequestIds.isEmpty()) {
            return List.of();
        }

        return notices.findByProgramRequestIdInAndStatusOrderByCreatedAtAsc(caseloadProgramRequestIds, "DRAFT")
                .stream()
                .map(notice -> NoticeReviewItemResponse.from(notice, readValidationResult(notice)))
                .toList();
    }

    @PostMapping("/api/cases/notices/{noticeId}/approve")
    NoticeResponse approve(@PathVariable UUID noticeId, Authentication authentication) {
        checkCaseloadAccess(noticeId, authentication);
        return NoticeResponse.from(noticeService.approve(noticeId, authentication.getName()));
    }

    @PostMapping("/api/cases/notices/{noticeId}/reject")
    NoticeResponse reject(@PathVariable UUID noticeId, Authentication authentication) {
        checkCaseloadAccess(noticeId, authentication);
        return NoticeResponse.from(noticeService.reject(noticeId, authentication.getName()));
    }

    private void checkCaseloadAccess(UUID noticeId, Authentication authentication) {
        Notice notice = noticeService.findById(noticeId);
        Household household = householdFor(notice.getProgramRequestId());
        caseAssignmentService.checkCaseloadAccess(household.getId(), authentication);
    }

    private Household householdFor(UUID programRequestId) {
        ProgramRequest programRequest = programRequests.findById(programRequestId).orElseThrow();
        Application application = applications.findById(programRequest.getApplicationId()).orElseThrow();
        return households.findById(application.getHouseholdId()).orElseThrow();
    }

    private JsonNode readValidationResult(Notice notice) {
        try {
            return objectMapper.readTree(notice.getValidationResult());
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "failed to parse stored validation_result JSON for notice " + notice.getId(), e);
        }
    }
}
