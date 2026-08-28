package canopica.api.document;

import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import canopica.api.domain.IncomeRecord;
import canopica.api.domain.Verification;
import canopica.api.pgmq.PgmqService;
import canopica.api.repo.DocumentRepository;
import canopica.api.repo.IncomeRecordRepository;
import canopica.api.repo.VerificationRepository;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.access.AccessDeniedException;
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
    private final VerificationRepository verifications;
    private final IncomeRecordRepository incomeRecords;
    private final AuditService auditService;
    private final PgmqService pgmq;
    private final Clock clock;

    DocumentService(
            S3Client s3,
            @Value("${canopica.minio.bucket}") String bucket,
            DocumentRepository documents,
            VerificationRepository verifications,
            IncomeRecordRepository incomeRecords,
            AuditService auditService,
            PgmqService pgmq,
            Clock clock) {
        this.s3 = s3;
        this.bucket = bucket;
        this.documents = documents;
        this.verifications = verifications;
        this.incomeRecords = incomeRecords;
        this.auditService = auditService;
        this.pgmq = pgmq;
        this.clock = clock;
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

    /**
     * The mandatory human-confirmation gate design doc §2.3 requires with no confidence-based bypass:
     * {@code satisfiedVerificationIds} and {@code incomeRecordsToPost} are the worker's own final,
     * edited-or-accepted values, never the raw extraction -- this method never reads {@code document.
     * extraction} itself. Applies them through the exact same repository calls a caseworker's manual entry
     * already uses ({@link IncomeRecordRepository#save}, {@link VerificationRepository#updateStatus}), the
     * same pattern {@link canopica.api.verification.MockVerificationService#requestVerification} already
     * establishes for appending a REQUESTED/RECEIVED pair of the same event type -- here, a CLASSIFIED/
     * CONFIRMED pair of {@link AuditEventType#DOCUMENT_CLASSIFIED}, distinguished by the payload's own
     * {@code stage}, not a new enum value.
     *
     * <p>{@code householdHeadPersonId} and every {@code satisfiedVerificationIds} entry are re-checked
     * against this document's own case here, not just trusted from the request body: the controller's own
     * {@link canopica.api.caseload.CaseAssignmentService#checkCaseloadAccess} only proves the caller may act
     * on <em>this document's</em> case, not that any UUID named inside the request body belongs to it too.
     * Without this check a worker legitimately confirming a document on their own caseload could name a
     * {@code satisfiedVerificationIds} entry or income {@code personId} from a case outside their caseload
     * entirely, and this method would silently mutate it -- a cross-case IDOR, not just a validation gap.
     */
    @Transactional
    public Document confirm(UUID documentId, List<UUID> satisfiedVerificationIds,
            List<ConfirmedIncome> incomeRecordsToPost, UUID householdHeadPersonId, String actorId) {
        Document document = documents.findById(documentId)
                .orElseThrow(() -> new NoSuchElementException("no document with id " + documentId));

        for (ConfirmedIncome income : incomeRecordsToPost) {
            if (!income.personId().equals(householdHeadPersonId)) {
                throw new AccessDeniedException(
                        "person " + income.personId() + " is not the head of this document's own household");
            }
            incomeRecords.save(new IncomeRecord(UUID.randomUUID(), income.personId(), income.incomeType(),
                    income.earned(), income.monthlyAmount(), income.effectiveFrom(), income.effectiveTo()));
        }

        LocalDate today = LocalDate.now(clock);
        for (UUID verificationId : satisfiedVerificationIds) {
            Verification verification = verifications.findById(verificationId)
                    .orElseThrow(() -> new NoSuchElementException("no verification with id " + verificationId));
            if (!verification.getProgramRequestId().equals(document.getProgramRequestId())) {
                throw new AccessDeniedException(
                        "verification " + verificationId + " does not belong to this document's own case");
            }
            verifications.updateStatus(verificationId, "RECEIVED", today);
            Map<String, Object> verificationPayload = new LinkedHashMap<>();
            verificationPayload.put("stage", "RECEIVED");
            verificationPayload.put("source", "DOCUMENT_CONFIRMATION");
            verificationPayload.put("document_id", documentId.toString());
            auditService.append(
                    AuditEventType.VERIFICATION_UPDATED, actorId, "verification", verificationId, verificationPayload);
        }

        documents.updateClassificationStatus(documentId, "CONFIRMED");
        Map<String, Object> confirmedPayload = new LinkedHashMap<>();
        confirmedPayload.put("stage", "CONFIRMED");
        confirmedPayload.put("document_id", documentId.toString());
        confirmedPayload.put("satisfied_verification_ids", satisfiedVerificationIds.stream().map(UUID::toString).toList());
        auditService.append(AuditEventType.DOCUMENT_CLASSIFIED, actorId, "program_request",
                document.getProgramRequestId(), confirmedPayload);

        return documents.findById(documentId).orElseThrow();
    }

    /** A worker-confirmed income figure to post via {@link IncomeRecordRepository#save} on confirm. */
    public record ConfirmedIncome(UUID personId, String incomeType, boolean earned, BigDecimal monthlyAmount,
            LocalDate effectiveFrom, LocalDate effectiveTo) {
    }
}
