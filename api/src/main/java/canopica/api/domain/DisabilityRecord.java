package canopica.api.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Effective-dated. "Disabled" for SNAP purposes is tied to receipt of a
 * qualifying benefit, not a self-reported status.
 */
@Entity
@Table(name = "disability_record")
public class DisabilityRecord {

    @Id
    private UUID id;

    @Column(name = "person_id", nullable = false)
    private UUID personId;

    @Column(name = "basis", nullable = false)
    private String basis;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected DisabilityRecord() {
        // JPA
    }

    public DisabilityRecord(UUID id, UUID personId, String basis, LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.personId = personId;
        this.basis = basis;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getPersonId() {
        return personId;
    }

    public String getBasis() {
        return basis;
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
