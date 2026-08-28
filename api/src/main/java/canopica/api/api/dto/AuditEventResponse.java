package canopica.api.api.dto;

import canopica.api.audit.AuditEventRecord;
import java.time.Instant;
import java.util.Map;

public record AuditEventResponse(
        String eventType, Instant occurredAt, String actorId, String actorType, Map<String, Object> payload) {

    public static AuditEventResponse from(AuditEventRecord record) {
        String actorType = "SYSTEM".equals(record.actorId()) ? "SYSTEM" : "HUMAN";
        return new AuditEventResponse(
                record.eventType().name(), record.occurredAt(), record.actorId(), actorType, record.payload());
    }
}
