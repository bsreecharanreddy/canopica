package ies.portal.policy;

import ies.rules.SnapPolicyParameters;
import java.time.LocalDate;

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
}
