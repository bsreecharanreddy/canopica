package canopica.api.notice;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * An AI-drafted eligibility notice awaiting review (Phase 3 design doc §2.4/§2.6). The row itself is written
 * by the Python worker's {@code correspondence_consumer.py} via a raw insert, the same split {@link
 * canopica.api.document.Document}'s own {@code extraction} fields already establish -- Java never drafts a
 * notice. Task 6 adds the one thing Java does own: the human review decision, exposed as two intent-named
 * transitions rather than setters, the same reasoning {@code PolicyParameterProposal}'s own doc comment
 * gives -- no code path can mark a notice reviewed twice or set a status with no reviewer attribution.
 */
@Entity
@Table(name = "notice")
public class Notice {

    @Id
    private UUID id;

    @Column(name = "program_request_id", nullable = false)
    private UUID programRequestId;

    @Column(name = "determination_id", nullable = false)
    private UUID determinationId;

    @Column(name = "notice_type", nullable = false)
    private String noticeType;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "content", nullable = false)
    private String content;

    @Column(name = "template_version", nullable = false)
    private String templateVersion;

    @Column(name = "language", nullable = false)
    private String language;

    @Column(name = "validation_result", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String validationResult;

    @Column(name = "generation_model", nullable = false)
    private String generationModel;

    @Column(name = "prompt_version", nullable = false)
    private String promptVersion;

    @Column(name = "approved_by")
    private String approvedBy;

    @Column(name = "approved_at")
    private Instant approvedAt;

    @Column(name = "sent_at")
    private Instant sentAt;

    @Column(name = "rejected_by")
    private String rejectedBy;

    @Column(name = "rejected_at")
    private Instant rejectedAt;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Notice() {
        // JPA
    }

    /**
     * Approving a draft dispatches it in the same step -- design doc §2.4's "dispatch" is generated, never
     * actually delivered (tradeoffs doc §4.4's unrevisited limitation: no records management for the sent
     * artifact), so this project has no separate later "send" action for a row to wait in APPROVED for.
     * {@code status} goes straight to {@code SENT}, satisfying V20's own {@code notice_approved_together}
     * check the same way a two-step flow would.
     */
    public void approveAndSend(String approvedBy, Instant now) {
        requireDraft();
        this.status = "SENT";
        this.approvedBy = approvedBy;
        this.approvedAt = now;
        this.sentAt = now;
    }

    public void reject(String rejectedBy, Instant now) {
        requireDraft();
        this.status = "REJECTED";
        this.rejectedBy = rejectedBy;
        this.rejectedAt = now;
    }

    /** A second reviewer must not be able to re-decide an already-reviewed notice. */
    private void requireDraft() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("notice " + id + " was already reviewed (" + status + ")");
        }
    }

    public UUID getId() {
        return id;
    }

    public UUID getProgramRequestId() {
        return programRequestId;
    }

    public UUID getDeterminationId() {
        return determinationId;
    }

    public String getNoticeType() {
        return noticeType;
    }

    public String getStatus() {
        return status;
    }

    public String getContent() {
        return content;
    }

    public String getTemplateVersion() {
        return templateVersion;
    }

    public String getLanguage() {
        return language;
    }

    public String getValidationResult() {
        return validationResult;
    }

    public String getGenerationModel() {
        return generationModel;
    }

    public String getPromptVersion() {
        return promptVersion;
    }

    public String getApprovedBy() {
        return approvedBy;
    }

    public Instant getApprovedAt() {
        return approvedAt;
    }

    public Instant getSentAt() {
        return sentAt;
    }

    public String getRejectedBy() {
        return rejectedBy;
    }

    public Instant getRejectedAt() {
        return rejectedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
