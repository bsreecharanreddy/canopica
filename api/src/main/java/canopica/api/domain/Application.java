package canopica.api.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * The customer-facing submission. Requests one or more programs, each tracked
 * separately as a PROGRAM_REQUEST.
 */
@Entity
@Table(name = "application")
public class Application {

    @Id
    private UUID id;

    @Column(name = "household_id", nullable = false)
    private UUID householdId;

    @Column(name = "submitted_at")
    private Instant submittedAt;

    @Column(name = "channel", nullable = false)
    private String channel;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Application() {
        // JPA
    }

    public Application(UUID id, UUID householdId, Instant submittedAt, String channel) {
        this.id = id;
        this.householdId = householdId;
        this.submittedAt = submittedAt;
        this.channel = channel;
    }

    public UUID getId() {
        return id;
    }

    public UUID getHouseholdId() {
        return householdId;
    }

    public Instant getSubmittedAt() {
        return submittedAt;
    }

    public String getChannel() {
        return channel;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
