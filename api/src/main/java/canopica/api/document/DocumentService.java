package canopica.api.document;

import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import canopica.api.pgmq.PgmqService;
import canopica.api.repo.DocumentRepository;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * Stores an uploaded document and enqueues its classification (Phase 3 design doc §2.1/§2.2). The MinIO
 * write happens first, outside the database transaction -- object storage is not transactional with
 * Postgres, so ordering matters: uploading first and only then committing the {@code document} row, the
 * {@code DOCUMENT_UPLOADED} audit event, and the {@code pgmq.send} together means a DB failure can only ever
 * leave an <em>orphaned, unreferenced</em> object (harmless -- matches the tradeoffs doc's already-accepted
 * "stored, not managed" limitation), never a {@code document} row pointing at an object that was never
 * actually written.
 */
@Service
public class DocumentService {

    private final S3Client s3;
    private final String bucket;
    private final DocumentRepository documents;
    private final AuditService auditService;
    private final PgmqService pgmq;

    DocumentService(
            S3Client s3,
            @Value("${canopica.minio.bucket}") String bucket,
            DocumentRepository documents,
            AuditService auditService,
            PgmqService pgmq) {
        this.s3 = s3;
        this.bucket = bucket;
        this.documents = documents;
        this.auditService = auditService;
        this.pgmq = pgmq;
    }

    @Transactional
    public Document upload(UUID programRequestId, MultipartFile file, String uploadedBy) {
        UUID id = UUID.randomUUID();
        // Derived from programRequestId and this document's own generated id
        // only -- never the uploaded filename (design doc §2.1's stated
        // reason: an applicant-controlled filename must not be able to
        // traverse or collide with another case's object).
        String objectKey = programRequestId + "/" + id;
        String contentType = file.getContentType() != null ? file.getContentType() : "application/octet-stream";

        putObject(objectKey, contentType, file);

        Document document = new Document(id, programRequestId, objectKey, contentType, uploadedBy);
        documents.save(document);
        auditService.append(AuditEventType.DOCUMENT_UPLOADED, uploadedBy, "program_request", programRequestId,
                Map.of("document_id", id.toString(), "content_type", contentType));
        pgmq.send("document_intake", Map.of("document_id", id.toString()));
        return document;
    }

    private void putObject(String objectKey, String contentType, MultipartFile file) {
        try {
            s3.putObject(
                    PutObjectRequest.builder().bucket(bucket).key(objectKey).contentType(contentType).build(),
                    RequestBody.fromInputStream(file.getInputStream(), file.getSize()));
        } catch (IOException e) {
            throw new UncheckedIOException("failed to read uploaded document", e);
        }
    }
}
