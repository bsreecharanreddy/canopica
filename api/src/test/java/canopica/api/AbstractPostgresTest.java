package canopica.api;

import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Testcontainers;

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

    // 16-alpine -> 18-alpine (Phase 3 Task 1): infra/docker-compose.yml's own
    // postgres service moved to a pgmq-bundled Postgres 18 image so the
    // worker's pgmq queues can exist -- this repo's API never calls pgmq
    // itself, so this container doesn't need that extension, but staying on
    // 18 keeps every Postgres surface in the stack on the same major
    // version rather than silently diverging from what local dev/CI's own
    // compose-based Postgres now runs.
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:18-alpine")
                    .withDatabaseName("canopica_operational")
                    .withUsername("canopica_app")
                    .withPassword("canopica_app");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
