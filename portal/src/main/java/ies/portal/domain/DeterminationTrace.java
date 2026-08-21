package ies.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Persists the full DMN evaluation: the input snapshot as of decision time,
 * which rules fired, and every intermediate value. A Phase 1a deliverable
 * precisely because Phase 2's policy Q&A and Phase 4's QC assistant both
 * already assume it exists (roadmap doc §3.4.1).
 */
@Entity
@Table(name = "determination_trace")
public class DeterminationTrace {

    @Id
    private UUID id;

    @Column(name = "determination_id", nullable = false, unique = true)
    private UUID determinationId;

    @Column(name = "input_snapshot", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String inputSnapshot;

    @Column(name = "decision_results", nullable = false)
    @JdbcTypeCode(SqlTypes.JSON)
    private String decisionResults;

    @Column(name = "dmn_model_name", nullable = false)
    private String dmnModelName;

    @Column(name = "dmn_model_hash", nullable = false)
    private String dmnModelHash;

    @Column(name = "engine_version", nullable = false)
    private String engineVersion;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected DeterminationTrace() {
        // JPA
    }

    public DeterminationTrace(UUID id, UUID determinationId, String inputSnapshot,
                               String decisionResults, String dmnModelName, String dmnModelHash,
                               String engineVersion) {
        this.id = id;
        this.determinationId = determinationId;
        this.inputSnapshot = inputSnapshot;
        this.decisionResults = decisionResults;
        this.dmnModelName = dmnModelName;
        this.dmnModelHash = dmnModelHash;
        this.engineVersion = engineVersion;
    }

    public UUID getId() {
        return id;
    }

    public UUID getDeterminationId() {
        return determinationId;
    }

    public String getInputSnapshot() {
        return inputSnapshot;
    }

    public String getDecisionResults() {
        return decisionResults;
    }

    public String getDmnModelName() {
        return dmnModelName;
    }

    public String getDmnModelHash() {
        return dmnModelHash;
    }

    public String getEngineVersion() {
        return engineVersion;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
