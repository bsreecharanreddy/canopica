package canopica.portal.api;

import canopica.portal.api.dto.ParameterProposalResponse;
import canopica.portal.api.dto.ProposeParameterChangesRequest;
import canopica.portal.api.dto.ReviewProposalRequest;
import canopica.portal.domain.PolicyParameterProposal;
import canopica.portal.policy.PolicyParameterPublishService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * The rule-authoring copilot's review workflow (Phase 2 design doc §2.3). ADMIN-only, gated in
 * {@code SecurityConfig} for all of {@code /api/policy/**} -- publishing a parameter version is a
 * higher-stakes action than the caseload work WORKER/SUPERVISOR do, so it gets the narrowest existing role.
 *
 * <p>There is deliberately no endpoint that publishes without a review: {@link #propose} only drafts, and
 * {@link #review} is the sole route to {@code PolicyParameterPublishService.accept}. The reviewer's identity
 * is the authenticated principal, never a field in the request body -- a caller cannot name someone else as
 * the person who approved a benefit figure.
 */
@RestController
@RequestMapping("/api/policy/proposals")
class PolicyParameterProposalController {

    private final PolicyParameterPublishService publishService;

    PolicyParameterProposalController(PolicyParameterPublishService publishService) {
        this.publishService = publishService;
    }

    @PostMapping
    ParameterProposalResponse propose(
            @Valid @RequestBody ProposeParameterChangesRequest request, Principal principal) {
        return respond(publishService.proposeAgainstEffectiveSet(request.documentExcerpt(), principal.getName()));
    }

    @GetMapping
    List<ParameterProposalResponse> list(
            @RequestParam(defaultValue = "PENDING") PolicyParameterProposal.Status status) {
        return publishService.findByStatus(status).stream().map(this::respond).toList();
    }

    @PostMapping("/{proposalId}/review")
    ParameterProposalResponse review(@PathVariable UUID proposalId,
            @Valid @RequestBody ReviewProposalRequest request, Principal principal) {
        PolicyParameterProposal reviewed = request.accept()
                ? publishService.accept(proposalId, principal.getName(), request.publicationDetails())
                : publishService.reject(proposalId, principal.getName());
        return respond(reviewed);
    }

    private ParameterProposalResponse respond(PolicyParameterProposal proposal) {
        return ParameterProposalResponse.from(
                proposal, publishService.versionLabelOf(proposal.getCurrentParameterSetId()));
    }
}
