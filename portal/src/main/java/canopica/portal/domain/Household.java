package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "household")
public class Household {

    @Id
    private UUID id;

    @Column(name = "head_person_id", nullable = false)
    private UUID headPersonId;

    @Column(name = "county", nullable = false)
    private String county;

    @Column(name = "address_line1", nullable = false)
    private String addressLine1;

    @Column(name = "address_line2")
    private String addressLine2;

    @Column(name = "city", nullable = false)
    private String city;

    @Column(name = "state", nullable = false)
    private String state;

    @Column(name = "zip_code", nullable = false)
    private String zipCode;

    // Both DB-managed past creation: false/null on insert (matching the column defaults), settable only
    // through the SUPERVISOR-only /api/supervisor/households/{id}/sensitivity endpoint's direct UPDATE --
    // never through this entity's own constructor/save path (design doc §2.1, flag-and-log not sealing).
    @Column(name = "is_sensitive", insertable = false, updatable = false)
    private boolean isSensitive;

    @Column(name = "sensitive_reason", insertable = false, updatable = false)
    private String sensitiveReason;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Household() {
        // JPA
    }

    public Household(UUID id, UUID headPersonId, String county, String addressLine1,
                      String addressLine2, String city, String state, String zipCode) {
        this.id = id;
        this.headPersonId = headPersonId;
        this.county = county;
        this.addressLine1 = addressLine1;
        this.addressLine2 = addressLine2;
        this.city = city;
        this.state = state;
        this.zipCode = zipCode;
    }

    public UUID getId() {
        return id;
    }

    public UUID getHeadPersonId() {
        return headPersonId;
    }

    public String getCounty() {
        return county;
    }

    public String getAddressLine1() {
        return addressLine1;
    }

    public String getAddressLine2() {
        return addressLine2;
    }

    public String getCity() {
        return city;
    }

    public String getState() {
        return state;
    }

    public String getZipCode() {
        return zipCode;
    }

    public boolean isSensitive() {
        return isSensitive;
    }

    public String getSensitiveReason() {
        return sensitiveReason;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
