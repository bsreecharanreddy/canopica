package canopica.api.api.dto;

import canopica.api.document.Document;
import java.time.Instant;
import java.util.UUID;

public record DocumentResponse(
        UUID id, UUID programRequestId, String contentType, String classificationStatus, Instant uploadedAt) {
    public static DocumentResponse from(Document document) {
        return new DocumentResponse(
                document.getId(), document.getProgramRequestId(), document.getContentType(),
                document.getClassificationStatus(), document.getUploadedAt());
    }
}
