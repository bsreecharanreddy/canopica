package ies.portal.audit;

import java.util.Map;
import java.util.UUID;

/**
 * Appends events to the hash-chained {@code audit_event} table (V6
 * migration). Deliberately does not, and cannot, set {@code prev_hash} or
 * {@code hash} -- the database computes both in a trigger under an advisory
 * lock, so the application supplies a payload and nothing else (roadmap
 * doc §3.6).
 */
public interface AuditService {

    void append(AuditEventType type, String actorId, String subjectType, UUID subjectId, Map<String, Object> payload);
}
