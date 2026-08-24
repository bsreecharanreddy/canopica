package canopica.portal.policy;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.http.client.ClientHttpRequestFactoryBuilder;
import org.springframework.boot.http.client.ClientHttpRequestFactorySettings;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Calls the Python AI service's {@code POST /rule-authoring/propose}.
 *
 * <p>{@link RestClient} rather than {@code RestTemplate}: it is the current Spring blocking HTTP client, and
 * the first one this portal needs at all -- Phase 1b's external-verification interface is mocked in-process,
 * so nothing before now made an outbound call.
 *
 * <p>The timeout is generous by ordinary HTTP standards and deliberately so. Behind this endpoint is CPU-bound
 * local inference sharing a host with Postgres, Keycloak and OpenSearch; the same figure is set, for the same
 * measured reason, on the Python side ({@code canopica_ai.config.Settings.ollama_timeout_seconds}).
 */
@Component
class HttpRuleAuthoringClient implements RuleAuthoringClient {

    private final RestClient restClient;

    HttpRuleAuthoringClient(RestClient.Builder builder,
            @Value("${canopica.ai.rule-authoring-url}") String baseUrl,
            @Value("${canopica.ai.rule-authoring-timeout-seconds}") long timeoutSeconds) {
        ClientHttpRequestFactory requestFactory = ClientHttpRequestFactoryBuilder.detect()
                .build(ClientHttpRequestFactorySettings.defaults()
                        .withConnectTimeout(Duration.ofSeconds(10))
                        .withReadTimeout(Duration.ofSeconds(timeoutSeconds)));
        this.restClient = builder.baseUrl(baseUrl).requestFactory(requestFactory).build();
    }

    @Override
    public ParameterProposalDraft propose(String documentExcerpt, UUID currentParameterSetId,
            List<CurrentParameterValue> currentValues) {
        try {
            ParameterProposalDraft draft = restClient.post()
                    .uri("/rule-authoring/propose")
                    .body(Map.of(
                            "documentExcerpt", documentExcerpt,
                            "currentParameterSetId", currentParameterSetId,
                            "currentValues", currentValues))
                    .retrieve()
                    .body(ParameterProposalDraft.class);
            if (draft == null) {
                throw new RuleAuthoringUnavailableException(
                        "rule-authoring copilot returned an empty body", null);
            }
            return draft;
        } catch (RestClientException e) {
            // Covers both "unreachable" and the service's own 502 ("ran, could not produce a valid
            // proposal") -- see RuleAuthoringUnavailableException for why one type serves both.
            throw new RuleAuthoringUnavailableException(
                    "rule-authoring copilot could not produce a proposal: " + e.getMessage(), e);
        }
    }
}
