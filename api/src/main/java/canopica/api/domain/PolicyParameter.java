package canopica.api.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.util.UUID;

/**
 * One named figure within a {@link PolicyParameterSet}. A null household
 * size means the value is scalar (a rate or a threshold); a non-null size
 * means it applies to exactly that household size (roadmap doc's numbers-
 * vs-logic split -- see the rules-engine README for the logic half).
 */
@Entity
@Table(name = "policy_parameter")
public class PolicyParameter {

    @Id
    private UUID id;

    @Column(name = "parameter_set_id", nullable = false)
    private UUID parameterSetId;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "household_size")
    private Integer householdSize;

    @Column(name = "numeric_value", nullable = false)
    private BigDecimal numericValue;

    @Column(name = "unit", nullable = false)
    private String unit;

    protected PolicyParameter() {
        // JPA
    }

    /**
     * The only way to create a figure in Java. Insert-only by construction -- there is no setter, and V3's
     * trigger refuses UPDATE and DELETE outright, unnarrowed by V15. Superseding a value means inserting it
     * again under a new {@link PolicyParameterSet}, which is what determination reproducibility rests on.
     */
    public PolicyParameter(UUID id, UUID parameterSetId, String name, Integer householdSize,
            BigDecimal numericValue, String unit) {
        this.id = id;
        this.parameterSetId = parameterSetId;
        this.name = name;
        this.householdSize = householdSize;
        this.numericValue = numericValue;
        this.unit = unit;
    }

    /** Copies this figure into a superseding set, optionally with a new value. */
    public PolicyParameter copyInto(UUID newParameterSetId, BigDecimal value) {
        return new PolicyParameter(UUID.randomUUID(), newParameterSetId, name, householdSize, value, unit);
    }

    public UUID getId() {
        return id;
    }

    public UUID getParameterSetId() {
        return parameterSetId;
    }

    public String getName() {
        return name;
    }

    public Integer getHouseholdSize() {
        return householdSize;
    }

    public BigDecimal getNumericValue() {
        return numericValue;
    }

    public String getUnit() {
        return unit;
    }
}
