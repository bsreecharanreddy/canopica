package canopica.api.audit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
class JdbcAuditService implements AuditService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    JdbcAuditService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Override
    public void append(AuditEventType type, String actorId, String subjectType, UUID subjectId,
                        Map<String, Object> payload) {
        jdbc.update(
                "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
                        + "values (?, ?, ?, ?, ?::jsonb)",
                type.name(), actorId, subjectType, subjectId, writeJson(payload));
    }

    private String writeJson(Map<String, Object> payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to serialize audit event payload", e);
        }
    }
}
