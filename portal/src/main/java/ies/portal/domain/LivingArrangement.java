package ies.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Effective-dated shelter situation for a household.
 */
@Entity
@Table(name = "living_arrangement")
public class LivingArrangement {

    @Id
    private UUID id;

    @Column(name = "household_id", nullable = false)
    private UUID householdId;

    @Column(name = "arrangement_type", nullable = false)
    private String arrangementType;

    @Column(name = "pays_utilities_separately", nullable = false)
    private boolean paysUtilitiesSeparately;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected LivingArrangement() {
        // JPA
    }

    public LivingArrangement(UUID id, UUID householdId, String arrangementType, boolean paysUtilitiesSeparately, LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.householdId = householdId;
        this.arrangementType = arrangementType;
        this.paysUtilitiesSeparately = paysUtilitiesSeparately;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getHouseholdId() {
        return householdId;
    }

    public String getArrangementType() {
        return arrangementType;
    }

    public boolean isPaysUtilitiesSeparately() {
        return paysUtilitiesSeparately;
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
