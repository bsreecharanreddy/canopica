package canopica.api.api.dto;

import canopica.api.notice.Notice;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.UUID;

/**
 * One review-queue row (Task 6). {@code validationResult} is Task 5's own deterministic pre-check output --
 * passed through as {@link JsonNode} rather than a typed field, the same "don't re-map a nested blob into a
 * typed DTO" convention {@link DocumentReviewItemResponse} already established for {@code extraction}, so
 * the review UI can show a failed check's own {@code errors} array without a second endpoint.
 */
public record NoticeReviewItemResponse(
        UUID noticeId, UUID programRequestId, String noticeType, String status, String content,
        JsonNode validationResult, String generationModel, String promptVersion, Instant createdAt) {

    public static NoticeReviewItemResponse from(Notice notice, JsonNode validationResult) {
        return new NoticeReviewItemResponse(
                notice.getId(), notice.getProgramRequestId(), notice.getNoticeType(), notice.getStatus(),
                notice.getContent(), validationResult, notice.getGenerationModel(), notice.getPromptVersion(),
                notice.getCreatedAt());
    }
}
