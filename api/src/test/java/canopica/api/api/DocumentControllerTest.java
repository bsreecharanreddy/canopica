package canopica.api.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import canopica.api.AbstractApiTest;
import canopica.api.CaseFixtures;
import canopica.api.document.DocumentService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.util.UUID;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
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
