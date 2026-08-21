package ies.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * An effective-dated, immutable-once-published set of SNAP figures (V3/V4
 * migrations enforce immutability at the database level, not just here).
 * Superseding a fiscal year is an insert of the next set, never an edit.
 */
@Entity
@Table(name = "policy_parameter_set")
public class PolicyParameterSet {

    @Id
    private UUID id;

    @Column(name = "program_code", nullable = false)
    private String programCode;

    @Column(name = "version_label", nullable = false, unique = true)
    private String versionLabel;

    @Column(name = "effective_from", nullable = false)
    private LocalDate effectiveFrom;

    @Column(name = "effective_to")
    private LocalDate effectiveTo;

    @Column(name = "source_citation", nullable = false)
    private String sourceCitation;

    @Column(name = "retrieved_on", nullable = false)
    private LocalDate retrievedOn;

    @Column(name = "published_at", insertable = false, updatable = false)
    private Instant publishedAt;

    protected PolicyParameterSet() {
        // JPA
    }

    public UUID getId() {
        return id;
    }

    public String getProgramCode() {
        return programCode;
    }

    public String getVersionLabel() {
        return versionLabel;
    }

    public LocalDate getEffectiveFrom() {
        return effectiveFrom;
    }

    public LocalDate getEffectiveTo() {
        return effectiveTo;
    }

    public String getSourceCitation() {
        return sourceCitation;
    }

    public LocalDate getRetrievedOn() {
        return retrievedOn;
    }

    public Instant getPublishedAt() {
        return publishedAt;
    }
}
