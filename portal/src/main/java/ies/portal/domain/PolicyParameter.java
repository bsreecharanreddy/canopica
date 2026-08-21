package ies.portal.domain;

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
