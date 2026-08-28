package canopica.api.api.dto;

import canopica.api.document.Document;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * One review-queue row (Task 4). {@code extraction} is the raw {@code DocumentExtraction} JSON the Python
 * worker wrote (Task 3) -- passed through as {@link JsonNode}, the same "don't re-map a nested blob into a
 * typed DTO" convention {@link TraceResponse} already established for {@code determination_trace}'s own
 * JSON columns. Its keys stay snake_case (Pydantic's own default), unlike this record's own fields.
 */
public record DocumentReviewItemResponse(
        UUID documentId, UUID programRequestId, String contentType, BigDecimal extractionConfidence,
        JsonNode extraction, Instant uploadedAt, UUID headPersonId, String householdHeadName) {

    public static DocumentReviewItemResponse from(
            Document document, JsonNode extraction, UUID headPersonId, String householdHeadName) {
        return new DocumentReviewItemResponse(
                document.getId(), document.getProgramRequestId(), document.getContentType(),
                document.getExtractionConfidence(), extraction, document.getUploadedAt(), headPersonId,
                householdHeadName);
    }
}
