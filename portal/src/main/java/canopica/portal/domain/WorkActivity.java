package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Effective-dated. Exemption reason drives ABAWD work requirement logic,
 * deferred past Phase 1a but modeled now.
 */
@Entity
@Table(name = "work_activity")
public class WorkActivity {

    @Id
    private UUID id;

    @Column(name = "person_id", nullable = false)
    private UUID personId;

    @Column(name = "activity_type", nullable = false)
    private String activityType;

    @Column(name = "weekly_hours", nullable = false)
    private int weeklyHours;

    @Column(name = "exemption_reason")
    private String exemptionReason;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected WorkActivity() {
        // JPA
    }

    public WorkActivity(UUID id, UUID personId, String activityType, int weeklyHours, String exemptionReason, LocalDate effectiveFrom, LocalDate effectiveTo) {
        this.id = id;
        this.personId = personId;
        this.activityType = activityType;
        this.weeklyHours = weeklyHours;
        this.exemptionReason = exemptionReason;
        this.effectiveFrom = effectiveFrom;
        this.effectiveTo = effectiveTo;
    }

    public UUID getId() {
        return id;
    }

    public UUID getPersonId() {
        return personId;
    }

    public String getActivityType() {
        return activityType;
    }

    public int getWeeklyHours() {
        return weeklyHours;
    }

    public String getExemptionReason() {
        return exemptionReason;
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
