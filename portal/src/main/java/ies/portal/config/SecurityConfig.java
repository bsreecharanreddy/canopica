package ies.portal.config;

import java.util.List;
import java.util.Map;
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
            @Value("${ies.keycloak.citizens-issuer-uri}") String citizensIssuerUri,
            @Value("${ies.keycloak.citizens-jwks-uri}") String citizensJwksUri)
            throws Exception {
        JwtDecoder decoder = lazyJwksDecoder(citizensJwksUri, citizensIssuerUri);
        http.securityMatcher(PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/api/applications"))
                .csrf(csrf -> csrf.disable()) // stateless, bearer-token API -- no browser session/cookie to forge
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("CUSTOMER"))
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                        jwt -> jwt.decoder(decoder).jwtAuthenticationConverter(citizenAuthenticationConverter())));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain workerFilterChain(
            HttpSecurity http,
            KeycloakWorkerSyncFilter keycloakWorkerSyncFilter,
            @Value("${ies.keycloak.workers-issuer-uri}") String workersIssuerUri,
            @Value("${ies.keycloak.workers-jwks-uri}") String workersJwksUri)
            throws Exception {
        JwtDecoder decoder = lazyJwksDecoder(workersJwksUri, workersIssuerUri);
        http.csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health")
                        .permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/program-requests/*/determinations")
                        .hasRole("WORKER")
                        .requestMatchers(HttpMethod.GET, "/api/program-requests/*")
                        .hasRole("WORKER")
                        .requestMatchers(HttpMethod.GET, "/api/determinations/*/trace")
                        .hasRole("WORKER")
                        .requestMatchers("/api/worker/**")
                        .hasRole("WORKER")
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
    // data loader -- all on the host, at localhost:8081), while portal-api itself can only reach Keycloak
    // via the container-network hostname (keycloak:8080) to fetch keys. Using
    // JwtDecoders.fromIssuerLocation() here (a single issuer-uri, used for both purposes) would demand
    // portal-api fetch its OIDC-discovery document from the very host:port whose issuer claim it's meant
    // to validate against -- unreachable from inside the container. NimbusJwtDecoder.withJwkSetUri() skips
    // discovery entirely and lets the two addresses differ, which is exactly what this split needs.
    //
    // The lazy wrapper below is separate insurance, not what fixes the above: it defers even this
    // (already-lazy) construction until first decode() call, so a test class that boots this same
    // @SpringBootTest context without needing MockMvc/security at all (schema tests, policy-parameter
    // tests...) never touches Keycloak, reachable or not.
    private static JwtDecoder lazyJwksDecoder(String jwksUri, String expectedIssuer) {
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
                            nimbusDecoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(expectedIssuer));
                            resolved = delegate = nimbusDecoder;
                        }
                    }
                }
                return resolved.decode(token);
            }
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
