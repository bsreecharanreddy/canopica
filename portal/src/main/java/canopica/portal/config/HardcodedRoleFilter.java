package canopica.portal.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Stands in for real identity until Phase 1b's Keycloak integration. Reads the {@code X-Canopica-Role} header
 * and, if it names a known role, sets a {@link UsernamePasswordAuthenticationToken} whose principal name
 * *is* the role string -- there is no other identity concept in Phase 1a, so controllers read
 * {@code Authentication#getName()} as the actor id honestly rather than inventing a fake user id. An
 * unknown or missing header rejects the request directly with {@code 401} here, before it ever reaches
 * Spring Security's own authorization checks (which only ever produce the role-mismatch {@code 403}).
 *
 * <p>Phase 1b replaces this one filter with real OIDC-backed authentication; nothing else in the security
 * chain, or any controller, needs to change when that happens.
 */
@Component
class HardcodedRoleFilter extends OncePerRequestFilter {

    private static final String ROLE_HEADER = "X-Canopica-Role";
    private static final Map<String, String> ROLE_HEADER_TO_AUTHORITY =
            Map.of("CUSTOMER", "ROLE_CUSTOMER", "WORKER", "ROLE_WORKER");

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        if ("/actuator/health".equals(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }

        String roleHeader = request.getHeader(ROLE_HEADER);
        String authority = roleHeader == null ? null : ROLE_HEADER_TO_AUTHORITY.get(roleHeader);
        if (authority == null) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "missing or unrecognized " + ROLE_HEADER + " header");
            return;
        }

        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
                roleHeader, null, List.of(new SimpleGrantedAuthority(authority))));
        filterChain.doFilter(request, response);
    }
}
