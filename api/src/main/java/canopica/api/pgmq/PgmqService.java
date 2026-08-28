package canopica.api.pgmq;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * A thin wrapper over pgmq's own {@code send} SQL function -- Phase 3 design doc §2.2's transactional-outbox
 * point made concrete: called from inside the same {@code @Transactional} method as the write it's about (a
 * {@code document} insert, an {@code eligibility_determination} commit), this shares that method's own JDBC
 * connection/transaction, so the enqueue can never succeed while the underlying write rolls back, or vice
 * versa -- no separate outbox table, no relay process. Same {@code JdbcTemplate} pattern {@link
 * canopica.api.audit.JdbcAuditService} already uses for a different table this project also owns no JPA
 * entity for by design.
 */
@Service
public class PgmqService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public PgmqService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    // pgmq.send is a SQL function that returns the new message's id (bigint), so this is a query, not a
    // DML statement -- jdbc.update() calls Statement.executeUpdate(), which the Postgres JDBC driver
    // rejects outright ("A result was returned when none was expected") for anything that produces a
    // result set, function calls included. Discovered for real by DocumentControllerTest (Task 2): the
    // worker's own Python pgmq.send call never hit this, since psycopg's execute()/fetchone() has no such
    // restriction -- this was a Java-JDBC-specific gap Task 1's own tests couldn't have caught, since
    // nothing called PgmqService.send() through a real Spring context until Task 2 did.
    public void send(String queueName, Map<String, Object> message) {
        jdbc.queryForObject("select pgmq.send(?, ?::jsonb)", Long.class, queueName, writeJson(message));
    }

    private String writeJson(Map<String, Object> message) {
        try {
            return objectMapper.writeValueAsString(message);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to serialize pgmq message", e);
        }
    }
}
