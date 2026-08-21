package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * The binding record: program, benefit month, eligible yes/no, benefit
 * amount, the parameter-set version used, decided-at, decided-by, and a
 * foreign key to its trace (roadmap doc §3.4.1). Append-only -- a changed
 * circumstance produces a NEW row here, never an edit; V5's trigger enforces
 * that at the database level, not just by convention.
 */
@Entity
@Table(name = "eligibility_determination")
public class EligibilityDetermination {

    @Id
    private UUID id;

    @Column(name = "program_request_id", nullable = false)
    private UUID programRequestId;

    @Column(name = "benefit_month", nullable = false)
    private LocalDate benefitMonth;

    @Column(name = "as_of_date", nullable = false)
    private LocalDate asOfDate;

    @Column(name = "eligible", nullable = false)
    private boolean eligible;

    @Column(name = "benefit_amount", nullable = false)
    private BigDecimal benefitAmount;

    @Column(name = "reason_code", nullable = false)
    private String reasonCode;

    @Column(name = "policy_parameter_set_id", nullable = false)
    private UUID policyParameterSetId;

    @Column(name = "policy_parameter_version", nullable = false)
    private String policyParameterVersion;

    @Column(name = "decided_at", insertable = false, updatable = false)
    private Instant decidedAt;

    @Column(name = "decided_by", nullable = false)
    private String decidedBy;

    protected EligibilityDetermination() {
        // JPA
    }

    public EligibilityDetermination(UUID id, UUID programRequestId, LocalDate benefitMonth,
                                     LocalDate asOfDate, boolean eligible, BigDecimal benefitAmount,
                                     String reasonCode, UUID policyParameterSetId,
                                     String policyParameterVersion, String decidedBy) {
        this.id = id;
        this.programRequestId = programRequestId;
        this.benefitMonth = benefitMonth;
        this.asOfDate = asOfDate;
        this.eligible = eligible;
        this.benefitAmount = benefitAmount;
        this.reasonCode = reasonCode;
        this.policyParameterSetId = policyParameterSetId;
        this.policyParameterVersion = policyParameterVersion;
        this.decidedBy = decidedBy;
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

    public LocalDate getAsOfDate() {
        return asOfDate;
    }

    public boolean isEligible() {
        return eligible;
    }

    public BigDecimal getBenefitAmount() {
        return benefitAmount;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public UUID getPolicyParameterSetId() {
        return policyParameterSetId;
    }

    public String getPolicyParameterVersion() {
        return policyParameterVersion;
    }

    public Instant getDecidedAt() {
        return decidedAt;
    }

    public String getDecidedBy() {
        return decidedBy;
    }
}
