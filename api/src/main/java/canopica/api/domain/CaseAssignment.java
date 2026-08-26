package canopica.api.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Effective-dated. What makes caseload-scoped row-level authorization possible
 * at all in Phase 1b -- without this, there is nothing to filter on.
 */
@Entity
@Table(name = "case_assignment")
public class CaseAssignment {

    @Id
    private UUID id;

    @Column(name = "household_id", nullable = false)
    private UUID householdId;

    @Column(name = "worker_id", nullable = false)
    private UUID workerId;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected CaseAssignment() {
        // JPA
    }

    public CaseAssignment(UUID id, UUID householdId, UUID workerId, LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.householdId = householdId;
        this.workerId = workerId;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getHouseholdId() {
        return householdId;
    }

    public UUID getWorkerId() {
        return workerId;
    }

    public LocalDate getEffectiveFrom() {
        return effectiveFrom;
    }

    public LocalDate getEffectiveTo() {
        return effectiveTo;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
