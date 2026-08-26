package canopica.api.policy;

import java.util.List;
import java.util.UUID;

/**
 * What the rule-authoring copilot hands back: a diff, plus enough provenance to answer "which model, under
 * which prompt, from which excerpt" about a figure that may end up deciding a benefit amount.
 *
 * <p>Mirrors {@code canopica_ai.policy_intelligence.rule_authoring.schema.ParameterProposal}. The two are kept
 * honest by {@code ai/tests/test_rule_authoring_api.py}, which asserts the exact camelCase wire shape this
 * binds to -- nothing else crosses that seam, since {@code PolicyParameterPublishServiceTest} stubs the
 * client interface rather than the HTTP call.
 */
public record ParameterProposalDraft(
        UUID parameterSetId,
        List<ProposedParameterValue> proposedValues,
        String sourceExcerpt,
        String generationModel,
        String promptVersion) {}
