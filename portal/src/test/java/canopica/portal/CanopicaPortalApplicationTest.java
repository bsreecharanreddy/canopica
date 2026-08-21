package canopica.portal;

import org.junit.jupiter.api.Test;

/**
 * Proves the full Spring context starts against a real Postgres instance --
 * migrations, JPA, and every {@code @Component} together. From Task 2
 * onward the app fundamentally requires a database to start, so this
 * extends {@link AbstractPostgresTest} rather than excluding
 * datasource/JPA autoconfiguration the way Task 1's version did.
 */
class CanopicaPortalApplicationTest extends AbstractPostgresTest {

    @Test
    void contextLoads() {
    }
}
