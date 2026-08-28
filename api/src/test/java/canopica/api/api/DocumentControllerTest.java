package canopica.api.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import canopica.api.CaseFixtures;
import canopica.api.document.DocumentService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.net.URI;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.MinIOContainer;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/**
 * Exercises the real {@code POST /api/cases/{programRequestId}/documents} endpoint end to end: a real
 * MinIO container (same singleton-container pattern {@link AbstractApiTest}'s own KEYCLOAK and {@link
 * canopica.api.AbstractPostgresTest}'s POSTGRES already use), a real object written and read back, the
 * real {@code document} row, and the real {@code pgmq.q_document_intake} queue table -- not a mocked
 * S3Client, matching this repo's "hit the real thing" testing standard everywhere else.
 */
class DocumentControllerTest extends AbstractApiTest {

    private static final String BUCKET = "canopica-documents";

    static final MinIOContainer MINIO = new MinIOContainer("minio/minio:RELEASE.2025-09-07T16-13-09Z");

    static {
        MINIO.start();
    }

    @DynamicPropertySource
    static void minioProperties(DynamicPropertyRegistry registry) {
        registry.add("canopica.minio.endpoint", MINIO::getS3URL);
        registry.add("canopica.minio.access-key", MINIO::getUserName);
        registry.add("canopica.minio.secret-key", MINIO::getPassword);
        registry.add("canopica.minio.bucket", () -> BUCKET);
    }

    @BeforeAll
    static void createBucket() {
        try (S3Client s3 = S3Client.builder()
                .endpointOverride(URI.create(MINIO.getS3URL()))
                .credentialsProvider(
                        StaticCredentialsProvider.create(AwsBasicCredentials.create(MINIO.getUserName(), MINIO.getPassword())))
                .region(Region.US_EAST_1)
                .forcePathStyle(true)
                .build()) {
            s3.createBucket(b -> b.bucket(BUCKET));
        }
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper objectMapper;
    @Autowired S3Client s3Client;
    @Autowired DocumentService documentService;

    @Test
    void uploadStoresTheObjectInsertsADocumentRowAppendsAuditAndEnqueuesClassification() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        byte[] content = "income report contents".getBytes();
        MockMultipartFile file = new MockMultipartFile("file", "income-report.pdf", "application/pdf", content);

        String response = mvc.perform(multipart("/api/cases/" + ids.programRequestId() + "/documents")
                        .file(file)
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.contentType").value("application/pdf"))
                .andExpect(jsonPath("$.classificationStatus").value("PENDING"))
                .andReturn().getResponse().getContentAsString();

        JsonNode json = objectMapper.readTree(response);
        UUID documentId = UUID.fromString(json.get("id").asText());

        String objectKey = jdbc.queryForObject(
                "select object_key from document where id = ?", String.class, documentId);
        assertThat(objectKey).isEqualTo(ids.programRequestId() + "/" + documentId);

        try (ResponseInputStream<GetObjectResponse> object =
                s3Client.getObject(GetObjectRequest.builder().bucket(BUCKET).key(objectKey).build())) {
            assertThat(object.readAllBytes()).isEqualTo(content);
        }

        assertThat(jdbc.queryForObject(
                "select count(*) from audit_event where event_type = 'DOCUMENT_UPLOADED' and subject_id = ?",
                Integer.class, ids.programRequestId())).isEqualTo(1);

        assertThat(jdbc.queryForObject(
                "select count(*) from pgmq.q_document_intake where message->>'document_id' = ?",
                Integer.class, documentId.toString())).isEqualTo(1);
    }

    @Test
    void uploadIsForbiddenForAWorkerNotHoldingTheActiveAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else Entirely", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), otherWorkerId);
        MockMultipartFile file = new MockMultipartFile("file", "income-report.pdf", "application/pdf", "content".getBytes());

        mvc.perform(multipart("/api/cases/" + ids.programRequestId() + "/documents")
                        .file(file)
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void reviewQueueIncludesOnlyThisWorkersOwnCaseloadOrderedByConfidenceAscending() throws Exception {
        // Triggers KeycloakWorkerSyncFilter's lazy provisioning of worker.sam's row, the same idiom
        // WorkerCaseControllerTest's own dashboard test uses, before this test needs its id.
        mvc.perform(get("/api/worker/cases").header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk());
        UUID samWorkerId = jdbc.queryForObject(
                "select id from worker where email = ?", UUID.class, "worker.sam@canopica.local");

        var mineLowConfidence = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var mineHighConfidence = CaseFixtures.threePersonWorkingHousehold(jdbc);
        var notMine = CaseFixtures.threePersonWorkingHousehold(jdbc);
        CaseFixtures.insertCaseAssignment(jdbc, mineLowConfidence.householdId(), samWorkerId);
        CaseFixtures.insertCaseAssignment(jdbc, mineHighConfidence.householdId(), samWorkerId);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Not Sam", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, notMine.householdId(), otherWorkerId);

        UUID lowConfidenceDocId = CaseFixtures.insertClassifiedDocument(
                jdbc, mineLowConfidence.programRequestId(), minimalIncomeExtraction(), new BigDecimal("0.300"));
        UUID highConfidenceDocId = CaseFixtures.insertClassifiedDocument(
                jdbc, mineHighConfidence.programRequestId(), minimalIncomeExtraction(), new BigDecimal("0.900"));
        UUID notMineDocId = CaseFixtures.insertClassifiedDocument(
                jdbc, notMine.programRequestId(), minimalIncomeExtraction(), new BigDecimal("0.100"));

        String response = mvc.perform(get("/api/cases/documents/review-queue")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken()))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode items = objectMapper.readTree(response);

        assertThat(indexOfDocument(items, notMineDocId))
                .as("a document from a household outside this worker's caseload must not appear")
                .isEqualTo(-1);
        long lowIndex = indexOfDocument(items, lowConfidenceDocId);
        long highIndex = indexOfDocument(items, highConfidenceDocId);
        assertThat(lowIndex).as("this worker's own low-confidence document must be present").isNotEqualTo(-1);
        assertThat(highIndex).as("this worker's own high-confidence document must be present").isNotEqualTo(-1);
        assertThat(lowIndex).as("lowest confidence surfaces first").isLessThan(highIndex);
    }

    @Test
    void confirmIsForbiddenForAWorkerNotHoldingTheActiveAssignment() throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID otherWorkerId = CaseFixtures.insertWorker(jdbc, "Someone Else Confirming", "WORKER");
        CaseFixtures.insertCaseAssignment(jdbc, ids.householdId(), otherWorkerId);
        UUID documentId = CaseFixtures.insertClassifiedDocument(
                jdbc, ids.programRequestId(), minimalIncomeExtraction(), new BigDecimal("0.500"));

        mvc.perform(post("/api/cases/documents/" + documentId + "/confirm")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"satisfiedVerificationIds\":[],\"incomeRecords\":[]}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void confirmAppliesIncomeAndVerificationValuesThroughTheExistingWritePathsAndMarksTheDocumentConfirmed()
            throws Exception {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID verificationId = CaseFixtures.insertVerification(jdbc, ids.programRequestId(), "INCOME");
        UUID documentId = CaseFixtures.insertClassifiedDocument(
                jdbc, ids.programRequestId(), minimalIncomeExtraction(), new BigDecimal("0.900"));

        String requestBody = "{"
                + "\"satisfiedVerificationIds\":[\"" + verificationId + "\"],"
                + "\"incomeRecords\":[{"
                + "\"personId\":\"" + ids.headPersonId() + "\","
                + "\"incomeType\":\"WAGES\",\"earned\":true,\"monthlyAmount\":1600.00,"
                + "\"effectiveFrom\":\"2025-02-01\",\"effectiveTo\":null}]}";

        mvc.perform(post("/api/cases/documents/" + documentId + "/confirm")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + workerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.classificationStatus").value("CONFIRMED"));

        assertThat(jdbc.queryForObject(
                        "select count(*) from income_record where person_id = ? and monthly_amount = 1600.00 "
                                + "and effective_from = ?",
                        Integer.class, ids.headPersonId(), LocalDate.of(2025, 2, 1)))
                .as("the confirmed income figure must be posted through IncomeRecordRepository, exactly like intake")
                .isEqualTo(1);

        assertThat(jdbc.queryForObject(
                        "select status from verification where id = ?", String.class, verificationId))
                .isEqualTo("RECEIVED");
        assertThat(jdbc.queryForObject(
                        "select satisfied_on from verification where id = ?", LocalDate.class, verificationId))
                .isNotNull();

        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where event_type = 'VERIFICATION_UPDATED' "
                                + "and subject_id = ? and payload->>'stage' = 'RECEIVED' "
                                + "and payload->>'source' = 'DOCUMENT_CONFIRMATION'",
                        Integer.class, verificationId))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject(
                        "select count(*) from audit_event where event_type = 'DOCUMENT_CLASSIFIED' "
                                + "and subject_id = ? and payload->>'stage' = 'CONFIRMED'",
                        Integer.class, ids.programRequestId()))
                .isEqualTo(1);
    }

    private String minimalIncomeExtraction() {
        return "{\"document_type\":\"INCOME_REPORT\",\"fields\":"
                + "[{\"name\":\"monthly_amount\",\"value\":\"1600.00\",\"confidence\":0.9}],"
                + "\"matched_verification_ids\":[],\"generation_model\":\"llama3.2:3b\",\"prompt_version\":\"v1\"}";
    }

    private long indexOfDocument(JsonNode items, UUID documentId) {
        long i = 0;
        for (JsonNode item : items) {
            if (item.get("documentId").asText().equals(documentId.toString())) {
                return i;
            }
            i++;
        }
        return -1;
    }

    @Test
    void aDbFailurePartwayThroughLeavesNoDocumentRowAndNoQueuedMessage() {
        // Calls DocumentService directly, bypassing DocumentController's own findById().orElseThrow() --
        // that pre-check would 404 before ever reaching the transactional method under test here. A
        // nonexistent programRequestId still lets the MinIO write (outside the DB transaction, per
        // DocumentService's own doc comment) succeed, then fails the document row insert on the real
        // program_request_id foreign key -- a genuine DB-level failure, not a mocked one.
        UUID nonexistentProgramRequestId = UUID.randomUUID();
        long queueDepthBefore = queueDepth();
        MockMultipartFile file = new MockMultipartFile("file", "orphan.pdf", "application/pdf", "content".getBytes());

        assertThrows(
                RuntimeException.class,
                () -> documentService.upload(nonexistentProgramRequestId, file, "worker.sam@canopica.local"));

        assertThat(jdbc.queryForObject(
                "select count(*) from document where program_request_id = ?", Integer.class, nonexistentProgramRequestId))
                .as("the document row must never exist for a program request that was never valid")
                .isEqualTo(0);
        assertThat(queueDepth())
                .as("no document_intake message should have been left behind by the rolled-back transaction")
                .isEqualTo(queueDepthBefore);
    }

    private long queueDepth() {
        Long count = jdbc.queryForObject("select count(*) from pgmq.q_document_intake", Long.class);
        return count == null ? 0 : count;
    }
}
