package canopica.api.config;

import canopica.api.domain.Person;
import canopica.api.repo.PersonRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Resolves a citizen-realm JWT's {@code sub} to the person id(s) it owns, once per request, mirroring the
 * read pattern {@link KeycloakWorkerSyncFilter} already established for the write case. No provisioning
 * here, unlike the worker filter -- a person row only ever exists because {@code IntakeService} already
 * created it at submission time, so there is no "first login creates the row" case to handle. Wired only
 * into {@link SecurityConfig}'s citizen chain, after JWT authentication has already populated the {@link
 * SecurityContextHolder}.
 */
@Component
public class KeycloakCitizenLinkFilter extends OncePerRequestFilter {

    // Public: read by canopica.api.api.CitizenController, a different package, to find whichever person
    // id(s) this request's caller owns without re-querying PersonRepository itself.
    public static final String PERSON_IDS_ATTRIBUTE = "canopica.citizen.personIds";

    private final PersonRepository persons;

    KeycloakCitizenLinkFilter(PersonRepository persons) {
        this.persons = persons;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication instanceof JwtAuthenticationToken jwtAuth) {
            List<UUID> personIds =
                    persons.findByKeycloakSubject(jwtAuth.getToken().getSubject()).stream().map(Person::getId).toList();
            request.setAttribute(PERSON_IDS_ATTRIBUTE, personIds);
        }
        filterChain.doFilter(request, response);
    }
}
