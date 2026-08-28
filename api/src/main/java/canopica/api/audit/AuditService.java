package canopica.api.audit;

import java.util.List;
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

    /**
     * Every event recorded against one subject, ordered oldest first. Callers composing a case's full
     * story need more than one call: {@code APPLICATION_SUBMITTED}/{@code CASE_VIEWED} are keyed on the
     * program request itself ({@code "program_request"}), but {@code DETERMINATION_MADE} is keyed on the
     * determination's own id ({@code "eligibility_determination"}) -- there is no single subject that owns
     * every event a case ever produces.
     */
    List<AuditEventRecord> findBySubject(String subjectType, UUID subjectId);
}
