package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * One outstanding data element a program request needs confirmed, and how it
 * was satisfied.
 */
@Entity
@Table(name = "verification")
public class Verification {

    @Id
    private UUID id;

    @Column(name = "program_request_id", nullable = false)
    private UUID programRequestId;

    @Column(name = "data_element", nullable = false)
    private String dataElement;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "due_on", nullable = false)
    private LocalDate dueOn;

    @Column(name = "satisfied_on")
    private LocalDate satisfiedOn;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Verification() {
        // JPA
    }

    public Verification(UUID id, UUID programRequestId, String dataElement, String status, LocalDate dueOn, LocalDate satisfiedOn) {
        this.id = id;
        this.programRequestId = programRequestId;
        this.dataElement = dataElement;
        this.status = status;
        this.dueOn = dueOn;
        this.satisfiedOn = satisfiedOn;
    }

    public UUID getId() {
        return id;
    }

    public UUID getProgramRequestId() {
        return programRequestId;
    }

    public String getDataElement() {
        return dataElement;
    }

    public String getStatus() {
        return status;
    }

    public LocalDate getDueOn() {
        return dueOn;
    }

    public LocalDate getSatisfiedOn() {
        return satisfiedOn;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
