package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Effective-dated: household composition changes constantly (a member moves
 * out, a child is born) and the model must be able to answer "who was in this
 * household on a given date," not just "who is in it now."
 */
@Entity
@Table(name = "household_member")
public class HouseholdMember {

    @Id
    private UUID id;

    @Column(name = "household_id", nullable = false)
    private UUID householdId;

    @Column(name = "person_id", nullable = false)
    private UUID personId;

    @Column(name = "relationship", nullable = false)
    private String relationship;

    @Column(name = "purchases_and_prepares_food_together", nullable = false)
    private boolean purchasesAndPreparesFoodTogether;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected HouseholdMember() {
        // JPA
    }

    public HouseholdMember(UUID id, UUID householdId, UUID personId, String relationship,
                            boolean purchasesAndPreparesFoodTogether,
                            LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.householdId = householdId;
        this.personId = personId;
        this.relationship = relationship;
        this.purchasesAndPreparesFoodTogether = purchasesAndPreparesFoodTogether;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getHouseholdId() {
        return householdId;
    }

    public UUID getPersonId() {
        return personId;
    }

    public String getRelationship() {
        return relationship;
    }

    public boolean isPurchasesAndPreparesFoodTogether() {
        return purchasesAndPreparesFoodTogether;
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
