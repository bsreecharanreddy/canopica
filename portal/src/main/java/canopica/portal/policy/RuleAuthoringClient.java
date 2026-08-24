package canopica.portal.policy;

import java.util.List;
import java.util.UUID;

/**
 * The portal's view of the rule-authoring copilot (Phase 2 design doc §2.3) -- the first call this system
 * makes in the portal-to-AI direction; Task 2's Policy Q&A calls the other way.
 *
 * <p>An interface rather than a concrete HTTP client for the same reason {@link PolicyParameterResolver} is
 * one: {@code PolicyParameterPublishServiceTest} needs to drive the publish path -- the code that actually
 * writes benefit figures -- against staged proposals, deterministically, without a multi-gigabyte model in
 * the loop. The model's own behaviour is tested where it belongs, against a real model, in
 * {@code ai/tests/test_rule_authoring.py}.
 */
public interface RuleAuthoringClient {

    /**
     * @throws RuleAuthoringUnavailableException if the copilot cannot be reached, or declines to produce a
     *     proposal it can stand behind. The caller surfaces that to the admin rather than persisting a
     *     partial draft.
     */
    ParameterProposalDraft propose(String documentExcerpt, UUID currentParameterSetId,
            List<CurrentParameterValue> currentValues);
}
