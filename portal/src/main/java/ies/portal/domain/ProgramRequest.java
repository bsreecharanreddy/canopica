package ies.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * The unit of eligibility, not APPLICATION: one application commonly requests
 * several programs, each determined separately, on its own timeline, with its
 * own outcome (roadmap doc, domain model notes).
 */
@Entity
@Table(name = "program_request")
public class ProgramRequest {

    @Id
    private UUID id;

    @Column(name = "application_id", nullable = false)
    private UUID applicationId;

    @Column(name = "program_code", nullable = false)
    private String programCode;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "requested_on", nullable = false)
    private LocalDate requestedOn;

    @Column(name = "is_expedited", nullable = false)
    private boolean expedited;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected ProgramRequest() {
        // JPA
    }

    public ProgramRequest(UUID id, UUID applicationId, String programCode, String status, LocalDate requestedOn, boolean expedited) {
        this.id = id;
        this.applicationId = applicationId;
        this.programCode = programCode;
        this.status = status;
        this.requestedOn = requestedOn;
        this.expedited = expedited;
    }

    public UUID getId() {
        return id;
    }

    public UUID getApplicationId() {
        return applicationId;
    }

    public String getProgramCode() {
        return programCode;
    }

    public String getStatus() {
        return status;
    }

    public LocalDate getRequestedOn() {
        return requestedOn;
    }

    public boolean isExpedited() {
        return expedited;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
