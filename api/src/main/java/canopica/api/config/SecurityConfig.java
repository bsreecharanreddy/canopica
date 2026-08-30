package canopica.api.config;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

/**
 * Two OAuth2 resource-server chains, one per Keycloak realm, matched by request path -- the citizen-vs-worker
 * role split already maps cleanly onto disjoint endpoint sets (roadmap domain model), so there is no single
 * request that could belong to either. Replaces {@code HardcodedRoleFilter}; no controller changes -- every
 * controller still reads {@code Authentication#getName()}, which is now the JWT's real {@code sub} claim
 * instead of the literal role string Phase 1a used.
 */
@Configuration
class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain citizenFilterChain(
            HttpSecurity http,
            KeycloakCitizenLinkFilter keycloakCitizenLinkFilter,
            @Value("${canopica.keycloak.citizens-issuer-uri}") String citizensIssuerUri,
            @Value("${canopica.keycloak.citizens-jwks-uri}") String citizensJwksUri)
            throws Exception {
        JwtDecoder decoder = lazyJwksDecoder(citizensJwksUri, citizensIssuerUri);
        // Task 2 widened this chain from POST /api/applications alone to also cover the citizen's own
        // read routes -- still every one of them CUSTOMER-only; the ownership check itself (which
        // household(s) this specific caller may read) is data-driven, in CitizenController, the same
        // "role gate here, data-driven gate in the controller" split the worker chain's own comment
        // already documents for WorkerCaseController.
        http.securityMatchers(matchers -> matchers.requestMatchers(
                        PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/api/applications"),
                        PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.GET, "/api/my/program-requests"),
                        PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.GET, "/api/my/determinations/*/trace")))
                .csrf(csrf -> csrf.disable()) // stateless, bearer-token API -- no browser session/cookie to forge
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("CUSTOMER"))
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                        jwt -> jwt.decoder(decoder).jwtAuthenticationConverter(citizenAuthenticationConverter())))
                // Runs after JWT auth has populated the SecurityContext, so it can read the token's claims;
                // scoped to this chain only, mirroring keycloakWorkerSyncFilter's own wiring below.
                .addFilterAfter(keycloakCitizenLinkFilter, BearerTokenAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain workerFilterChain(
            HttpSecurity http,
            KeycloakWorkerSyncFilter keycloakWorkerSyncFilter,
            @Value("${canopica.keycloak.workers-issuer-uri}") String workersIssuerUri,
            @Value("${canopica.keycloak.workers-container-issuer-uri}") String workersContainerIssuerUri,
            @Value("${canopica.keycloak.workers-jwks-uri}") String workersJwksUri)
            throws Exception {
        // Two valid issuers, not one -- see application.yml's own comment on
        // workers-container-issuer-uri for why canopica-airflow's token carries a
        // genuinely different (but equally real) `iss` claim than the browser UI's.
        JwtDecoder decoder = lazyJwksDecoder(workersJwksUri, workersIssuerUri, workersContainerIssuerUri);
        http.csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health")
                        .permitAll()
                        // Prometheus (infra's `prometheus` service) has no JWT to present -- same
                        // "infra tooling, not a role-bearing caller" rationale as /actuator/health above.
                        .requestMatchers("/actuator/prometheus")
                        .permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/program-requests/*/determinations")
                        .hasRole("WORKER")
                        // A SUPERVISOR can view any case (design doc §2.1) -- the caseload-scoped check
                        // itself (assigned WORKER vs. anyone else) is data-driven, not role-based, so it
                        // lives in WorkerCaseController, not here; this gate only proves the *role* is
                        // allowed to reach these endpoints at all.
                        .requestMatchers(HttpMethod.GET, "/api/program-requests/*")
                        .hasAnyRole("WORKER", "SUPERVISOR")
                        .requestMatchers(HttpMethod.GET, "/api/determinations/*/trace")
                        .hasAnyRole("WORKER", "SUPERVISOR")
                        // "/api/program-requests/*" above matches exactly one path segment past the id, so
                        // it does not cover this nested resource -- needs its own entry. Same data-driven
                        // caseload check as case viewing (Task 2), reused wholesale by VerificationController
                        // rather than re-implemented, so a SUPERVISOR is allowed here too.
                        .requestMatchers("/api/program-requests/*/verifications/**")
                        .hasAnyRole("WORKER", "SUPERVISOR")
                        .requestMatchers("/api/supervisor/**")
                        .hasRole("SUPERVISOR")
                        // Fraud-risk review (Phase 4 Task 3). SUPERVISOR only, same narrowest-existing-role
                        // reasoning as /api/policy/** above -- no data-driven caseload check follows this one
                        // either, since the review queue is deliberately cross-caseload (design doc §2.9).
                        .requestMatchers("/api/fraud/**")
                        .hasRole("SUPERVISOR")
                        // Rule-authoring review (Phase 2 Task 3). ADMIN, not SUPERVISOR: publishing a
                        // parameter version changes the figures *every future determination* resolves
                        // against, which is a categorically bigger blast radius than the per-case work a
                        // SUPERVISOR does. Narrowest existing role wins; no data-driven check follows this
                        // one, because there is no per-case scoping to apply -- a parameter set is global.
                        .requestMatchers("/api/policy/**")
                        .hasRole("ADMIN")
                        // QC sample-trigger (Phase 4 Task 4). ADMIN, same reasoning as /api/policy/**
                        // above -- an internal, schedule-triggered operation (Airflow's own service-
                        // account client, canopica-airflow in the workers realm export), not a
                        // supervisor-facing one. Task 5's human review-queue endpoints land under
                        // /api/qc/** instead, a separate SUPERVISOR-scoped surface.
                        .requestMatchers("/api/internal/qc/**")
                        .hasRole("ADMIN")
                        // QC review queue (Phase 4 Task 5). SUPERVISOR, same role and "cross-caseload
                        // triage queue" reasoning as /api/fraud/** above -- no data-driven caseload check
                        // follows this one either.
                        .requestMatchers("/api/qc/**")
                        .hasRole("SUPERVISOR")
                        // Case SLA/Compliance Monitor (Phase 4 Task 6). SUPERVISOR, same role and
                        // cross-caseload triage-queue reasoning as /api/fraud/** and /api/qc/** above.
                        .requestMatchers("/api/sla/**")
                        .hasRole("SUPERVISOR")
                        .requestMatchers("/api/worker/**")
                        .hasAnyRole("WORKER", "SUPERVISOR")
                        .anyRequest()
                        .authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                        jwt -> jwt.decoder(decoder).jwtAuthenticationConverter(workerAuthenticationConverter())))
                // Runs after JWT auth has populated the SecurityContext, so it can read the token's claims;
                // scoped to this chain only -- citizens never need a `worker` row.
                .addFilterAfter(keycloakWorkerSyncFilter, BearerTokenAuthenticationFilter.class);
        return http.build();
    }

    // jwksUri (where to fetch signing keys -- must be network-reachable from wherever this app runs) is
    // deliberately separate from expectedIssuer (a pure comparison string against every token's own `iss`
    // claim). They're the same value in local dev, but not in Docker Compose: Keycloak stamps `iss` as
    // whichever address the *token-requesting* caller used to reach it (browser, test, or the synthetic-
    // data loader -- all on the host, at localhost:8081), while api itself can only reach Keycloak
    // via the container-network hostname (keycloak:8080) to fetch keys. Using
    // JwtDecoders.fromIssuerLocation() here (a single issuer-uri, used for both purposes) would demand
    // api fetch its OIDC-discovery document from the very host:port whose issuer claim it's meant
    // to validate against -- unreachable from inside the container. NimbusJwtDecoder.withJwkSetUri() skips
    // discovery entirely and lets the two addresses differ, which is exactly what this split needs.
    //
    // The lazy wrapper below is separate insurance, not what fixes the above: it defers even this
    // (already-lazy) construction until first decode() call, so a test class that boots this same
    // @SpringBootTest context without needing MockMvc/security at all (schema tests, policy-parameter
    // tests...) never touches Keycloak, reachable or not.
    //
    // expectedIssuers is variadic, not a single String, since Phase 4 Task 4's canopica-airflow
    // client broke the "every caller reaches Keycloak the same way" assumption the single-issuer
    // version of this method used to make (see application.yml's workers-container-issuer-uri
    // comment) -- a token is valid if its `iss` claim matches ANY of the caller's own known-real
    // addresses for this realm, not exactly one.
    private static JwtDecoder lazyJwksDecoder(String jwksUri, String... expectedIssuers) {
        Set<String> validIssuers = Set.of(expectedIssuers);
        return new JwtDecoder() {
            private volatile JwtDecoder delegate;

            @Override
            public Jwt decode(String token) {
                JwtDecoder resolved = delegate;
                if (resolved == null) {
                    synchronized (this) {
                        resolved = delegate;
                        if (resolved == null) {
                            NimbusJwtDecoder nimbusDecoder = NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
                            nimbusDecoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                                    JwtValidators.createDefault(), issuerIn(validIssuers)));
                            resolved = delegate = nimbusDecoder;
                        }
                    }
                }
                return resolved.decode(token);
            }
        };
    }

    // JwtValidators.createDefaultWithIssuer() only ever accepts exactly one issuer string; this is
    // the same check widened to a set, for the multi-issuer worker chain above (the citizens chain
    // still passes a single-element set, behaving identically to the original single-issuer check).
    private static OAuth2TokenValidator<Jwt> issuerIn(Set<String> validIssuers) {
        return jwt -> {
            String issuer = jwt.getIssuer() != null ? jwt.getIssuer().toString() : null;
            if (validIssuers.contains(issuer)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_issuer", "The iss claim " + issuer + " is not one of " + validIssuers, null));
        };
    }

    // Any validated token from the citizens realm is a customer -- there is only one kind of citizen
    // account, so no per-token role claim to read (unlike the worker realm's WORKER/SUPERVISOR/ADMIN split).
    private JwtAuthenticationConverter citizenAuthenticationConverter() {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> List.of(new SimpleGrantedAuthority("ROLE_CUSTOMER")));
        return converter;
    }

    private JwtAuthenticationConverter workerAuthenticationConverter() {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(SecurityConfig::realmRoleAuthorities);
        return converter;
    }

    // realm_access.roles is Keycloak's own standard shape for realm-level roles on an access token.
    @SuppressWarnings("unchecked")
    private static List<GrantedAuthority> realmRoleAuthorities(Jwt jwt) {
        Map<String, Object> realmAccess = jwt.getClaim("realm_access");
        if (realmAccess == null) {
            return List.of();
        }
        List<String> roles = (List<String>) realmAccess.getOrDefault("roles", List.of());
        return roles.stream()
                .map(role -> (GrantedAuthority) new SimpleGrantedAuthority("ROLE_" + role))
                .collect(Collectors.toList());
    }
}
