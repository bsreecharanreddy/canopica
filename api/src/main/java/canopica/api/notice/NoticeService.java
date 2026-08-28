package canopica.api.notice;

import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import canopica.api.repo.NoticeRepository;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Reads a {@link Notice} back for the case-facing review UI, and owns the one thing Java writes to this
 * table: the human review decision (Task 6). Nothing else writes a notice here -- the worker's {@code
 * correspondence_consumer.py} inserts the DRAFT row directly, the same split {@link
 * canopica.api.document.DocumentService}'s own {@code upload}/worker-write split establishes for {@code
 * document.extraction}.
 *
 * <p>A failed deterministic pre-check never blocks {@link #approve} -- the plan's own Step 3 requires the
 * check's result be shown, not enforced, since a human reviewing and deciding despite a flagged result is
 * still "a human reviewer owns the decision" (CLAUDE.md's governing principle), not a bypass of it.
 */
@Service
public class NoticeService {

    private final NoticeRepository notices;
    private final AuditService auditService;
    private final NoticePdfRenderer pdfRenderer;
    private final Clock clock;

    NoticeService(NoticeRepository notices, AuditService auditService, NoticePdfRenderer pdfRenderer, Clock clock) {
        this.notices = notices;
        this.auditService = auditService;
        this.pdfRenderer = pdfRenderer;
        this.clock = clock;
    }

    public Notice findById(UUID noticeId) {
        return notices.findById(noticeId)
                .orElseThrow(() -> new NoSuchElementException("no notice with id " + noticeId));
    }

    /**
     * Renders the approved content to PDF (proving the render pipeline works for real -- the bytes
     * themselves are not persisted, per the tradeoffs doc's unrevisited §4.4), then marks the notice SENT in
     * the same step {@link Notice#approveAndSend} always takes. Appends {@code NOTICE_APPROVED} then {@code
     * NOTICE_SENT} in that order, both in this one transaction, so the audit chain can never show one without
     * the other.
     */
    @Transactional
    public Notice approve(UUID noticeId, String approvedBy) {
        Notice notice = findById(noticeId);
        byte[] pdf = pdfRenderer.render(notice.getContent());
        if (pdf.length == 0) {
            throw new IllegalStateException("PDF rendering produced no bytes for notice " + noticeId);
        }

        notice.approveAndSend(approvedBy, clock.instant());
        Notice saved = notices.save(notice);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("notice_id", noticeId.toString());
        payload.put("notice_type", notice.getNoticeType());
        auditService.append(
                AuditEventType.NOTICE_APPROVED, approvedBy, "program_request", notice.getProgramRequestId(), payload);
        auditService.append(
                AuditEventType.NOTICE_SENT, approvedBy, "program_request", notice.getProgramRequestId(), payload);
        return saved;
    }

    /**
     * No PDF, no {@code NOTICE_SENT} -- matches {@code PolicyParameterPublishService#reject}'s own precedent
     * (only the consequential accept path gets an audit event there); a rejection changed nothing a
     * determination or an eventual delivery would ever read, so {@code rejected_by}/{@code rejected_at} on
     * the row itself carry the accountability, the same reviewedBy/reviewedAt symmetry {@code
     * PolicyParameterProposal} already holds for its own reject path.
     */
    @Transactional
    public Notice reject(UUID noticeId, String rejectedBy) {
        Notice notice = findById(noticeId);
        notice.reject(rejectedBy, clock.instant());
        return notices.save(notice);
    }
}
