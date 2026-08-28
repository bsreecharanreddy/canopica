package canopica.api.api.dto;

import canopica.api.notice.Notice;
import java.time.Instant;
import java.util.UUID;

public record NoticeResponse(
        UUID id, UUID programRequestId, String noticeType, String status, Instant approvedAt, Instant sentAt) {
    public static NoticeResponse from(Notice notice) {
        return new NoticeResponse(
                notice.getId(), notice.getProgramRequestId(), notice.getNoticeType(), notice.getStatus(),
                notice.getApprovedAt(), notice.getSentAt());
    }
}
