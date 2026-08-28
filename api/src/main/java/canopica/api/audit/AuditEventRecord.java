package canopica.api.audit;

import java.time.Instant;
import java.util.Map;

/** One row read back from {@code audit_event} -- the read-side counterpart to {@link AuditService#append}. */
public record AuditEventRecord(AuditEventType eventType, Instant occurredAt, String actorId, Map<String, Object> payload) {
}
