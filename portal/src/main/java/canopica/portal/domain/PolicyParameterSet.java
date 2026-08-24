package canopica.portal.domain;

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

    /**
     * Publishes a new, open-ended set. The only way to create one in Java -- every set that existed before
     * Phase 2 Task 3 was seeded by the V4 migration, and the only caller is {@code
     * PolicyParameterPublishService}'s accept path, after a human has approved the figures.
     *
     * <p>No {@code effectiveTo}: a newly published set is in force until something supersedes it, and
     * supersession is what {@link #closeAt} is for.
     */
    public PolicyParameterSet(UUID id, String programCode, String versionLabel, LocalDate effectiveFrom,
            String sourceCitation, LocalDate retrievedOn) {
        this.id = id;
        this.programCode = programCode;
        this.versionLabel = versionLabel;
        this.effectiveFrom = effectiveFrom;
        this.sourceCitation = sourceCitation;
        this.retrievedOn = retrievedOn;
    }

    /**
     * Closes an open-ended range, the one edit a published set permits (V15 migration; see
     * {@code docs/design/2026-08-23-policy-parameter-supersession.md}). One-way and one-shot: the guard here
     * and the trigger in the database say the same thing, so this cannot be reached past the trigger and the
     * trigger cannot be reached past this.
     */
    public void closeAt(LocalDate effectiveTo) {
        if (this.effectiveTo != null) {
            throw new IllegalStateException(
                    versionLabel + " is already closed at " + this.effectiveTo + " and cannot be reopened or moved");
        }
        if (effectiveTo.isBefore(effectiveFrom)) {
            throw new IllegalArgumentException(
                    versionLabel + " cannot end (" + effectiveTo + ") before it starts (" + effectiveFrom + ")");
        }
        this.effectiveTo = effectiveTo;
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
