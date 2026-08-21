package ies.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Roles are hardcoded in Phase 1a (see {@link HardcodedRoleFilter}), but expressed behind Spring
 * Security's normal {@link SecurityFilterChain}/{@code authorizeHttpRequests} abstractions, so Phase 1b
 * swaps one filter and nothing here or in any controller.
 */
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http, HardcodedRoleFilter hardcodedRoleFilter) throws Exception {
        http
                .csrf(csrf -> csrf.disable()) // stateless, header-authenticated JSON API -- no browser session/cookie to forge
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/applications").hasRole("CUSTOMER")
                        .requestMatchers(HttpMethod.POST, "/api/program-requests/*/determinations").hasRole("WORKER")
                        .requestMatchers(HttpMethod.GET, "/api/program-requests/*").hasRole("WORKER")
                        .requestMatchers(HttpMethod.GET, "/api/determinations/*/trace").hasRole("WORKER")
                        .requestMatchers("/api/worker/**").hasRole("WORKER")
                        .anyRequest().authenticated())
                .addFilterBefore(hardcodedRoleFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
