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
 * Effective-dated. Whether this is earned or unearned income drives the 20%
 * earned-income deduction, so it is stored, not inferred at evaluation time.
 */
@Entity
@Table(name = "income_record")
public class IncomeRecord {

    @Id
    private UUID id;

    @Column(name = "person_id", nullable = false)
    private UUID personId;

    @Column(name = "income_type", nullable = false)
    private String incomeType;

    @Column(name = "is_earned", nullable = false)
    private boolean earned;

    @Column(name = "monthly_amount", nullable = false)
    private BigDecimal monthlyAmount;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected IncomeRecord() {
        // JPA
    }

    public IncomeRecord(UUID id, UUID personId, String incomeType, boolean earned, BigDecimal monthlyAmount, LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.personId = personId;
        this.incomeType = incomeType;
        this.earned = earned;
        this.monthlyAmount = monthlyAmount;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getPersonId() {
        return personId;
    }

    public String getIncomeType() {
        return incomeType;
    }

    public boolean isEarned() {
        return earned;
    }

    public BigDecimal getMonthlyAmount() {
        return monthlyAmount;
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
