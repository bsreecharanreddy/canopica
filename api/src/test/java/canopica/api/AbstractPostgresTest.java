package canopica.api;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

/**
 * Base class for every test that needs a real Postgres instance. The container
 * is a static singleton started once per JVM (not per test class) so a full
 * Testcontainers suite does not pay a fresh-container cost per class; Flyway
 * runs its migrations against it on each Spring context start, same as it
 * would against a real environment. {@code @AutoConfigureMockMvc} wires a
 * {@code MockMvc} bean through Spring Security's real filter chain -- a no-op
 * for tests that don't inject it.
 */
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
public abstract class AbstractPostgresTest {

    // 16-alpine -> 18-alpine, then plain -> pgmq-bundled (Phase 3 Task 2):
    // DocumentService now calls PgmqService.send(...) directly, so this
    // container needs the real pgmq extension too, not just Postgres 18 --
    // the "API never calls pgmq itself" reasoning this comment used to give
    // stopped being true the moment Task 2 wired document upload to
    // pgmq.send. Same image infra/docker-compose.yml's real postgres
    // service and worker/tests/conftest.py's own Testcontainers fixture
    // already use, so every Postgres surface in the stack stays identical.
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>(DockerImageName.parse("ghcr.io/pgmq/pg18-pgmq:v1.10.0").asCompatibleSubstituteFor("postgres"))
                    .withDatabaseName("canopica_operational")
                    .withUsername("canopica_app")
                    .withPassword("canopica_app");

    static {
        POSTGRES.start();
        initializePgmq();
    }

    // Mirrors infra/postgres/init/01-databases.sql's bootstrap for the real
    // compose stack, run here instead against the ephemeral test container
    // directly via plain JDBC (no Spring context exists yet at this point in
    // static init). No explicit grants needed the way that init script
    // needs them for the real canopica_app role: Testcontainers' own
    // PostgreSQLContainer makes the withUsername() account the actual
    // Postgres superuser of this fresh, single-tenant container.
    private static void initializePgmq() {
        try (Connection connection = DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
                Statement statement = connection.createStatement()) {
            statement.execute("create extension if not exists pgmq cascade");
            statement.execute("select pgmq.create('document_intake')");
            statement.execute("select pgmq.create('correspondence_dispatch')");
        } catch (SQLException e) {
            throw new IllegalStateException("failed to initialize pgmq extension/queues in the test Postgres container", e);
        }
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
