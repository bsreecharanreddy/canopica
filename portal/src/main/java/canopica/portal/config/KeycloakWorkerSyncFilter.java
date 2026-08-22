package canopica.portal.config;

import canopica.portal.domain.Worker;
import canopica.portal.repo.WorkerRepository;
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
            String subject = jwt.getSubject();
            if (workers.findByKeycloakSubject(subject).isEmpty()) {
                workers.save(new Worker(UUID.randomUUID(), fullName(jwt), jwt.getClaimAsString("email"), primaryRealmRole(jwt), subject));
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
