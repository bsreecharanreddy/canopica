package canopica.api.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * A rule-authoring copilot's draft, awaiting a human decision (Phase 2 design doc §2.3).
 *
 * <p>The one deliberately <em>mutable</em> table in this corner of the schema, and the exception proves the
 * rule: it is a review-workflow record, not a published figure. Accepting a proposal never edits a parameter
 * -- it inserts a whole new {@link PolicyParameterSet} and records the fact here, in
 * {@code publishedParameterSetId}. V3's immutability trigger is deliberately not copied onto this table (see
 * the V14 migration's own comment).
 *
 * <p>Mutation is exposed as two intent-named transitions rather than setters, so there is no code path that
 * can set an arbitrary status, review a proposal without naming a reviewer, or mark one published without
 * having published anything. V14's CHECK constraints enforce the same invariants a second time, in the
 * database -- this class makes them hard to violate, the constraints make it impossible.
 */
@Entity
@Table(name = "policy_parameter_proposal")
public class PolicyParameterProposal {

    public enum Status {
        PENDING,
        ACCEPTED,
        REJECTED
    }

    @Id
    private UUID id;

    @Column(name = "current_parameter_set_id", nullable = false)
    private UUID currentParameterSetId;

    @Column(name = "source_excerpt", nullable = false)
    private String sourceExcerpt;

    @Column(name = "proposed_values", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String proposedValues;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "proposed_by", nullable = false)
    private String proposedBy;

    @Column(name = "reviewed_by")
    private String reviewedBy;

    @Column(name = "reviewed_at")
    private Instant reviewedAt;

    @Column(name = "published_parameter_set_id")
    private UUID publishedParameterSetId;

    @Column(name = "generation_model", nullable = false)
    private String generationModel;

    @Column(name = "prompt_version", nullable = false)
    private String promptVersion;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected PolicyParameterProposal() {
        // JPA
    }

    public PolicyParameterProposal(UUID id, UUID currentParameterSetId, String sourceExcerpt,
            String proposedValues, String proposedBy, String generationModel, String promptVersion) {
        this.id = id;
        this.currentParameterSetId = currentParameterSetId;
        this.sourceExcerpt = sourceExcerpt;
        this.proposedValues = proposedValues;
        this.proposedBy = proposedBy;
        this.generationModel = generationModel;
        this.promptVersion = promptVersion;
        this.status = Status.PENDING.name();
    }

    /** A decision names a reviewer and a time, or it has not happened. Both transitions below enforce that. */
    public void reject(String reviewerName, Instant reviewedAt) {
        requirePending();
        this.status = Status.REJECTED.name();
        this.reviewedBy = reviewerName;
        this.reviewedAt = reviewedAt;
    }

    public void accept(String reviewerName, Instant reviewedAt, UUID publishedParameterSetId) {
        requirePending();
        this.status = Status.ACCEPTED.name();
        this.reviewedBy = reviewerName;
        this.reviewedAt = reviewedAt;
        this.publishedParameterSetId = publishedParameterSetId;
    }

    /**
     * A second reviewer must not be able to re-decide a proposal, and in particular must not be able to
     * publish a second parameter set from a draft that has already been published once.
     */
    private void requirePending() {
        if (getStatus() != Status.PENDING) {
            throw new IllegalStateException("proposal " + id + " was already reviewed (" + status + ")");
        }
    }

    public UUID getId() {
        return id;
    }

    public UUID getCurrentParameterSetId() {
        return currentParameterSetId;
    }

    public String getSourceExcerpt() {
        return sourceExcerpt;
    }

    public String getProposedValues() {
        return proposedValues;
    }

    public Status getStatus() {
        return Status.valueOf(status);
    }

    public String getProposedBy() {
        return proposedBy;
    }

    public String getReviewedBy() {
        return reviewedBy;
    }

    public Instant getReviewedAt() {
        return reviewedAt;
    }

    public UUID getPublishedParameterSetId() {
        return publishedParameterSetId;
    }

    public String getGenerationModel() {
        return generationModel;
    }

    public String getPromptVersion() {
        return promptVersion;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
