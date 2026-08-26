package canopica.api.policy;

import canopica.rules.SnapPolicyParameters;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Resolves the effective-dated SNAP figures a determination should use.
 * Numbers live in the database (this class); logic lives in the DMN model
 * (rules-engine) -- see the rules-engine README for that boundary.
 */
public interface PolicyParameterResolver {

    /**
     * @throws PolicyParameterNotFoundException if no published SNAP
     *         parameter set covers {@code asOf}, or the covering set does
     *         not have figures for {@code householdSize}.
     */
    SnapPolicyParameters resolveSnap(LocalDate asOf, int householdSize);

    /**
     * Resolves against a specific, already-known parameter set rather than
     * by date. Used to reproduce a past determination exactly as it was
     * decided -- re-resolving by "today's" date would silently pick up a
     * later fiscal year's figures instead of the ones the original
     * determination actually used.
     *
     * @throws PolicyParameterNotFoundException if the set does not exist or
     *         does not have figures for {@code householdSize}.
     */
    SnapPolicyParameters resolveSnapByParameterSetId(UUID parameterSetId, int householdSize);
}
