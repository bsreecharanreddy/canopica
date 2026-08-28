package canopica.api.document;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * A system-of-record pointer into MinIO (Phase 3 design doc §2.6) -- the object itself is stored exactly as
 * uploaded, never overwritten by classification output. {@code classificationStatus} advances
 * PENDING -&gt; CLASSIFIED (Task 3's worker) -&gt; CONFIRMED/REJECTED (Task 4's worker review, the mandatory
 * human-confirmation gate design doc §2.3 requires with no confidence-based bypass).
 */
@Entity
@Table(name = "document")
public class Document {

    @Id
    private UUID id;

    @Column(name = "program_request_id", nullable = false)
    private UUID programRequestId;

    @Column(name = "object_key", nullable = false, unique = true)
    private String objectKey;

    @Column(name = "content_type", nullable = false)
    private String contentType;

    @Column(name = "uploaded_by", nullable = false)
    private String uploadedBy;

    @Column(name = "uploaded_at", insertable = false, updatable = false)
    private Instant uploadedAt;

    @Column(name = "classification_status", nullable = false)
    private String classificationStatus;

    protected Document() {
        // JPA
    }

    public Document(UUID id, UUID programRequestId, String objectKey, String contentType, String uploadedBy) {
        this.id = id;
        this.programRequestId = programRequestId;
        this.objectKey = objectKey;
        this.contentType = contentType;
        this.uploadedBy = uploadedBy;
        this.classificationStatus = "PENDING";
    }

    public UUID getId() {
        return id;
    }

    public UUID getProgramRequestId() {
        return programRequestId;
    }

    public String getObjectKey() {
        return objectKey;
    }

    public String getContentType() {
        return contentType;
    }

    public String getUploadedBy() {
        return uploadedBy;
    }

    public Instant getUploadedAt() {
        return uploadedAt;
    }

    public String getClassificationStatus() {
        return classificationStatus;
    }
}
