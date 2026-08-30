package canopica.api.config;

import canopica.api.domain.Worker;
import canopica.api.repo.WorkerRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * First-login provisioning: a worker-realm JWT with no matching {@code worker.keycloak_subject} gets a
 * {@link Worker} row created here, from the token's own claims -- there is no separate admin
 * "provision this worker" step, matching how a real caseworker account activates on first SSO login rather
 * than through a manual pre-registration step. Wired only into {@link SecurityConfig}'s worker chain, after
 * JWT authentication has already populated the {@link SecurityContextHolder}.
 *
 * <p>Deliberately does not sync a {@code client_credentials} service-account token (Phase 4 Task 4's
 * {@code canopica-airflow}, live-verified for real building Task 6): such a token carries no {@code email}
 * claim at all -- there is no human SSO login behind it for Keycloak to have populated one from -- and {@code
 * worker.email} is a real, intentional not-null constraint for the human accounts this filter otherwise
 * provisions. A machine caller is not a caseworker with a caseload; skipping it here is not a workaround for
 * the constraint, it is recognizing that this filter's whole premise (first-login SSO provisioning) does not
 * apply to it. Found live: this insert failed outright with a not-null violation the first time a real
 * {@code canopica-airflow} token ever reached this filter, which is exactly why it had gone uncaught -- Task
 * 4's own STATUS.md entry already stated "live Airflow trigger not manually exercised" as a known gap.
 */
@Component
class KeycloakWorkerSyncFilter extends OncePerRequestFilter {

    private final WorkerRepository workers;

    KeycloakWorkerSyncFilter(WorkerRepository workers) {
        this.workers = workers;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication instanceof JwtAuthenticationToken jwtAuth) {
            Jwt jwt = jwtAuth.getToken();
            String email = jwt.getClaimAsString("email");
            String subject = jwt.getSubject();
            if (email != null && workers.findByKeycloakSubject(subject).isEmpty()) {
                workers.save(new Worker(UUID.randomUUID(), fullName(jwt), email, primaryRealmRole(jwt), subject));
            }
        }
        filterChain.doFilter(request, response);
    }

    private static String fullName(Jwt jwt) {
        String givenName = jwt.getClaimAsString("given_name");
        String familyName = jwt.getClaimAsString("family_name");
        if (givenName != null && familyName != null) {
            return givenName + " " + familyName;
        }
        String preferredUsername = jwt.getClaimAsString("preferred_username");
        return preferredUsername != null ? preferredUsername : jwt.getSubject();
    }

    // Highest-privilege role wins if a token somehow carries more than one -- ADMIN > SUPERVISOR > WORKER.
    @SuppressWarnings("unchecked")
    private static String primaryRealmRole(Jwt jwt) {
        Map<String, Object> realmAccess = jwt.getClaim("realm_access");
        List<String> roles = realmAccess == null ? List.of() : (List<String>) realmAccess.getOrDefault("roles", List.of());
        if (roles.contains("ADMIN")) {
            return "ADMIN";
        }
        if (roles.contains("SUPERVISOR")) {
            return "SUPERVISOR";
        }
        return "WORKER";
    }
}
