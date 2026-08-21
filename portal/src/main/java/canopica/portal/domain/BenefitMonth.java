package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * One authorized benefit month for a program request. Always the first of the
 * month; benefits are computed per benefit month.
 */
@Entity
@Table(name = "benefit_month")
public class BenefitMonth {

    @Id
    private UUID id;

    @Column(name = "program_request_id", nullable = false)
    private UUID programRequestId;

    @Column(name = "benefit_month", nullable = false)
    private LocalDate benefitMonth;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected BenefitMonth() {
        // JPA
    }

    public BenefitMonth(UUID id, UUID programRequestId, LocalDate benefitMonth) {
        this.id = id;
        this.programRequestId = programRequestId;
        this.benefitMonth = benefitMonth;
    }

    public UUID getId() {
        return id;
    }

    public UUID getProgramRequestId() {
        return programRequestId;
    }

    public LocalDate getBenefitMonth() {
        return benefitMonth;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
