package ies.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Effective-dated household-level liquid resource (cash, bank account) --
 * unlike income/expense, this is counted per household, not per member.
 */
@Entity
@Table(name = "resource_record")
public class ResourceRecord {

    @Id
    private UUID id;

    @Column(name = "household_id", nullable = false)
    private UUID householdId;

    @Column(name = "resource_type", nullable = false)
    private String resourceType;

    @Column(name = "amount", nullable = false)
    private BigDecimal amount;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected ResourceRecord() {
        // JPA
    }

    public ResourceRecord(UUID id, UUID householdId, String resourceType, BigDecimal amount,
            LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.householdId = householdId;
        this.resourceType = resourceType;
        this.amount = amount;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getHouseholdId() {
        return householdId;
    }

    public String getResourceType() {
        return resourceType;
    }

    public BigDecimal getAmount() {
        return amount;
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
