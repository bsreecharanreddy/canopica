package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * A caseworker, supervisor, or admin. {@code role} mirrors the authenticated Keycloak realm role;
 * {@code keycloakSubject} is the JWT {@code sub} claim that maps a token back to this row, populated by
 * {@link canopica.portal.config.KeycloakWorkerSyncFilter} on first login rather than any admin provisioning step.
 */
@Entity
@Table(name = "worker")
public class Worker {

    @Id
    private UUID id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(name = "email", nullable = false, unique = true)
    private String email;

    @Column(name = "role", nullable = false)
    private String role;

    @Column(name = "keycloak_subject", unique = true)
    private String keycloakSubject;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Worker() {
        // JPA
    }

    public Worker(UUID id, String fullName, String email, String role, String keycloakSubject) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
        this.role = role;
        this.keycloakSubject = keycloakSubject;
    }

    public UUID getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public String getRole() {
        return role;
    }

    public String getKeycloakSubject() {
        return keycloakSubject;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
