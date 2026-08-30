package canopica.api.sop;

import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.http.client.ClientHttpRequestFactoryBuilder;
import org.springframework.boot.http.client.ClientHttpRequestFactorySettings;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Calls the Python AI service's {@code POST /sop-copilot/ask}. Same {@link RestClient}/generous-timeout
 * shape {@link canopica.api.policy.HttpRuleAuthoringClient} already establishes for a different AI capability
 * -- see that class's own doc comment for why the timeout is set this way (CPU-bound local inference sharing
 * a host with Postgres/Keycloak/OpenSearch).
 */
@Component
class HttpSopCopilotClient implements SopCopilotClient {

    private final RestClient restClient;

    HttpSopCopilotClient(RestClient.Builder builder,
            @Value("${canopica.ai.sop-copilot-url}") String baseUrl,
            @Value("${canopica.ai.sop-copilot-timeout-seconds}") long timeoutSeconds) {
        ClientHttpRequestFactory requestFactory = ClientHttpRequestFactoryBuilder.detect()
                .build(ClientHttpRequestFactorySettings.defaults()
                        .withConnectTimeout(Duration.ofSeconds(10))
                        .withReadTimeout(Duration.ofSeconds(timeoutSeconds)));
        this.restClient = builder.baseUrl(baseUrl).requestFactory(requestFactory).build();
    }

    @Override
    public SopAnswer ask(String question) {
        try {
            SopAnswer answer = restClient.post()
                    .uri("/sop-copilot/ask")
                    .body(Map.of("question", question))
                    .retrieve()
                    .body(SopAnswer.class);
            if (answer == null) {
                throw new SopCopilotUnavailableException("SOP copilot returned an empty body", null);
            }
            return answer;
        } catch (RestClientException e) {
            throw new SopCopilotUnavailableException(
                    "SOP copilot could not produce an answer: " + e.getMessage(), e);
        }
    }
}
