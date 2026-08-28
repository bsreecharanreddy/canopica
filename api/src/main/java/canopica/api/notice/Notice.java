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
 * An AI-drafted eligibility notice awaiting review (Phase 3 design doc §2.4/§2.6). Every row here is written
 * by the Python worker's {@code correspondence_consumer.py} via a raw insert, the same split {@link
 * canopica.api.document.Document}'s own {@code extraction} fields already establish -- this entity exists so
 * Java can read a notice back (the case-facing review UI, Task 6), not because Java ever drafts one itself.
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

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Notice() {
        // JPA
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

    public Instant getCreatedAt() {
        return createdAt;
    }
}
