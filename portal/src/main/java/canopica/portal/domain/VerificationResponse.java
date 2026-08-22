package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * The mock external verification interface's raw response to one {@link Verification} request. Never
 * surfaced to the CUSTOMER role or in any list view -- only {@code MockVerificationService} and the
 * detail path that resolves a single verification read {@code rawPayload} (design doc §2.2).
 */
@Entity
@Table(name = "verification_response")
public class VerificationResponse {

    @Id
    private UUID id;

    @Column(name = "verification_id", nullable = false)
    private UUID verificationId;

    @Column(name = "outcome", nullable = false)
    private String outcome;

    @Column(name = "raw_payload", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String rawPayload;

    @Column(name = "received_at", insertable = false, updatable = false)
    private Instant receivedAt;

    protected VerificationResponse() {
        // JPA
    }

    public VerificationResponse(UUID id, UUID verificationId, String outcome, String rawPayload) {
        this.id = id;
        this.verificationId = verificationId;
        this.outcome = outcome;
        this.rawPayload = rawPayload;
    }

    public UUID getId() {
        return id;
    }

    public UUID getVerificationId() {
        return verificationId;
    }

    public String getOutcome() {
        return outcome;
    }

    public String getRawPayload() {
        return rawPayload;
    }

    public Instant getReceivedAt() {
        return receivedAt;
    }
}
