package canopica.portal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dasniko.testcontainers.keycloak.KeycloakContainer;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpRequest.BodyPublishers;
import java.time.Duration;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Base for any test that makes an authenticated MockMvc call. Starts a real, singleton Keycloak container
 * (same JVM-wide-singleton pattern {@link AbstractPostgresTest#POSTGRES} already uses) importing this
 * repo's actual {@code identity/realm-export/} files -- copied onto the test classpath by
 * {@code portal/pom.xml}'s extra {@code testResources} entry, so this is the exact same realm config the
 * real {@code infra/docker-compose.yml} Keycloak service imports, not a parallel test-only approximation.
 *
 * <p>Token helpers fetch real access tokens via each realm's Direct Access Grant flow (the {@code
 * test-worker}/{@code test-customer} confidential clients, seeded test users) -- a real HTTP round trip to
 * a real running Keycloak, the same "hit the real thing" standard every other test base class in this repo
 * already holds to, not a hand-built or mocked JWT.
 */
public abstract class AbstractApiTest extends AbstractPostgresTest {

    static final KeycloakContainer KEYCLOAK =
            new KeycloakContainer("quay.io/keycloak/keycloak:26.4")
                    .withRealmImportFiles("keycloak/canopica-workers-realm.json", "keycloak/canopica-citizens-realm.json");

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();

    static {
        KEYCLOAK.start(); // singleton container, reused by every subclass -- same pattern as POSTGRES
    }

    // The whole test (token fetch + portal-api's own Spring context) runs in one JVM on the host, both
    // reaching this one Testcontainers-published address -- no internal-vs-external split needed here the
    // way infra/docker-compose.yml's real keycloak service needs one (see SecurityConfig.lazyJwksDecoder).
    @DynamicPropertySource
    static void keycloakProperties(DynamicPropertyRegistry registry) {
        registry.add("canopica.keycloak.workers-issuer-uri", () -> KEYCLOAK.getAuthServerUrl() + "/realms/canopica-workers");
        registry.add("canopica.keycloak.workers-jwks-uri",
                () -> KEYCLOAK.getAuthServerUrl() + "/realms/canopica-workers/protocol/openid-connect/certs");
        registry.add("canopica.keycloak.citizens-issuer-uri", () -> KEYCLOAK.getAuthServerUrl() + "/realms/canopica-citizens");
        registry.add("canopica.keycloak.citizens-jwks-uri",
                () -> KEYCLOAK.getAuthServerUrl() + "/realms/canopica-citizens/protocol/openid-connect/certs");
    }

    // Memoized: every test class sharing this singleton container reuses one token per role rather than
    // round-tripping Keycloak per test method. 900s access-token lifespan comfortably outlives one test run.
    private static String cachedWorkerToken;
    private static String cachedSupervisorToken;
    private static String cachedCitizenToken;
    private static String cachedOtherCitizenToken;

    protected static synchronized String workerToken() {
        if (cachedWorkerToken == null) {
            cachedWorkerToken = fetchToken("canopica-workers", "test-worker", "test-worker-secret", "worker.sam", "CanopicaWorker123!");
        }
        return cachedWorkerToken;
    }

    protected static synchronized String supervisorToken() {
        if (cachedSupervisorToken == null) {
            cachedSupervisorToken =
                    fetchToken("canopica-workers", "test-worker", "test-worker-secret", "supervisor.robin", "CanopicaSupervisor123!");
        }
        return cachedSupervisorToken;
    }

    protected static synchronized String citizenToken() {
        if (cachedCitizenToken == null) {
            cachedCitizenToken = fetchToken(
                    "canopica-citizens", "test-customer", "test-customer-secret", "citizen.jordan@canopica.local", "CanopicaCitizen123!");
        }
        return cachedCitizenToken;
    }

    // A second, distinct citizen identity -- needed to prove ownership checks actually deny a different
    // citizen, not just prove the same one succeeds.
    protected static synchronized String otherCitizenToken() {
        if (cachedOtherCitizenToken == null) {
            cachedOtherCitizenToken = fetchToken(
                    "canopica-citizens", "test-customer", "test-customer-secret", "citizen.morgan@canopica.local", "CanopicaCitizen456!");
        }
        return cachedOtherCitizenToken;
    }

    private static String fetchToken(String realm, String clientId, String clientSecret, String username, String password) {
        String body = "grant_type=password"
                + "&client_id=" + clientId
                + "&client_secret=" + clientSecret
                + "&username=" + username
                + "&password=" + password;
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(KEYCLOAK.getAuthServerUrl() + "/realms/" + realm + "/protocol/openid-connect/token"))
                .header("Content-Type", "application/x-www-form-urlencoded")
                .POST(BodyPublishers.ofString(body))
                .build();
        try {
            HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "token fetch for " + username + "@" + realm + " failed: " + response.statusCode() + " " + response.body());
            }
            JsonNode node = JSON.readTree(response.body());
            return node.get("access_token").asText();
        } catch (IOException | InterruptedException e) {
            throw new IllegalStateException("token fetch for " + username + "@" + realm + " failed", e);
        }
    }
}
