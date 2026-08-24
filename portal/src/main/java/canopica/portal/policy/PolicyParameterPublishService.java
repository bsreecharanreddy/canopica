package canopica.portal.policy;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.portal.audit.AuditEventType;
import canopica.portal.audit.AuditService;
import canopica.portal.domain.PolicyParameter;
import canopica.portal.domain.PolicyParameterProposal;
import canopica.portal.domain.PolicyParameterSet;
import canopica.portal.repo.PolicyParameterProposalRepository;
import canopica.portal.repo.PolicyParameterRepository;
import canopica.portal.repo.PolicyParameterSetRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Turns a rule-authoring draft into a published parameter set, but only across an explicit human decision.
 *
 * <p>This is where CLAUDE.md's governing principle stops being a slogan. {@link #propose} calls a model and
 * writes a row nothing reads for a determination; {@link #accept} writes figures the DMN engine will use to
 * decide real benefits, and it is reachable only from an ADMIN-authenticated review action naming the
 * reviewer. There is no path between the two that a model can take on its own.
 *
 * <p>Three properties the accept path holds, each of which would be a real defect to lose:
 *
 * <ul>
 *   <li><b>The new set is complete, not a delta.</b> Every figure is copied forward and the accepted changes
 *       applied over the top, because {@link PolicyParameterResolver} needs the whole list to build a
 *       {@code SnapPolicyParameters}.
 *   <li><b>Ranges never overlap.</b> The outgoing set is closed the day before the new one starts, in the
 *       same transaction, so there is no window in which two sets are in force -- which
 *       {@code findEffectiveOn} would surface as a failed determination, not a failed publish.
 *   <li><b>Nothing is trusted twice.</b> Every proposed value is re-validated here against the figure it
 *       replaces, even though the AI service validated it too. The two checks are on opposite sides of an
 *       HTTP boundary and neither is a substitute for the other.
 * </ul>
 */
@Service
public class PolicyParameterPublishService {

    private static final TypeReference<List<ProposedParameterValue>> PROPOSED_VALUES =
            new TypeReference<>() {};

    private final RuleAuthoringClient ruleAuthoringClient;
    private final PolicyParameterProposalRepository proposals;
    private final PolicyParameterSetRepository sets;
    private final PolicyParameterRepository parameters;
    private final AuditService auditService;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    PolicyParameterPublishService(RuleAuthoringClient ruleAuthoringClient,
            PolicyParameterProposalRepository proposals, PolicyParameterSetRepository sets,
            PolicyParameterRepository parameters, AuditService auditService, ObjectMapper objectMapper,
            Clock clock) {
        this.ruleAuthoringClient = ruleAuthoringClient;
        this.proposals = proposals;
        this.sets = sets;
        this.parameters = parameters;
        this.auditService = auditService;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    /**
     * Drafts against whatever set is in force today -- what an admin pasting a memo actually means, and one
     * less thing for a UI to have to know or get wrong.
     */
    @Transactional
    public PolicyParameterProposal proposeAgainstEffectiveSet(String documentExcerpt, String proposedBy) {
        PolicyParameterSet current = sets.findEffectiveOn("SNAP", LocalDate.now(clock)).orElseThrow(() ->
                new PolicyParameterNotFoundException(
                        "no published SNAP parameter set covers " + LocalDate.now(clock)));
        return propose(documentExcerpt, current.getId(), proposedBy);
    }

    /** The version label of the set a proposal is diffed against -- shown to the reviewer for context. */
    @Transactional(readOnly = true)
    public String versionLabelOf(UUID parameterSetId) {
        return requireSet(parameterSetId).getVersionLabel();
    }

    @Transactional(readOnly = true)
    public List<PolicyParameterProposal> findByStatus(PolicyParameterProposal.Status status) {
        return proposals.findByStatusOrderByCreatedAtDesc(status.name());
    }

    /**
     * Asks the copilot for a draft against a parameter set, and persists it as PENDING. Writes nothing any
     * determination can read.
     */
    @Transactional
    public PolicyParameterProposal propose(String documentExcerpt, UUID currentParameterSetId, String proposedBy) {
        PolicyParameterSet currentSet = requireSet(currentParameterSetId);
        List<CurrentParameterValue> currentValues =
                parameters.findByParameterSetIdOrderByNameAscHouseholdSizeAsc(currentSet.getId()).stream()
                        .map(CurrentParameterValue::from)
                        .toList();

        ParameterProposalDraft draft =
                ruleAuthoringClient.propose(documentExcerpt, currentSet.getId(), currentValues);
        // Validated on arrival rather than at accept time, so an admin never sees a diff line that cannot be
        // published -- the moment to find out a figure is impossible is before a human reasons about it.
        draft.proposedValues().forEach(PolicyParameterPublishService::validate);

        return proposals.save(new PolicyParameterProposal(
                UUID.randomUUID(),
                currentSet.getId(),
                documentExcerpt,
                writeJson(draft.proposedValues()),
                proposedBy,
                draft.generationModel(),
                draft.promptVersion()));
    }

    @Transactional
    public PolicyParameterProposal reject(UUID proposalId, String reviewerName) {
        PolicyParameterProposal proposal = requireProposal(proposalId);
        proposal.reject(reviewerName, clock.instant());
        return proposals.save(proposal);
    }

    /**
     * Publishes the proposal's figures as a new parameter set, in force from {@code details.effectiveFrom}.
     *
     * @param reviewerName the human accountable for this figure being in force -- recorded on the proposal
     *     row and, tamper-evidently, in the audit chain.
     */
    @Transactional
    public PolicyParameterProposal accept(UUID proposalId, String reviewerName, PublicationDetails details) {
        PolicyParameterProposal proposal = requireProposal(proposalId);
        PolicyParameterSet outgoing = requireSet(proposal.getCurrentParameterSetId());
        List<ProposedParameterValue> changes = readJson(proposal.getProposedValues());

        // Everything that can refuse this publish runs before anything is written. A rolled-back transaction
        // would undo a partial write anyway, but "validate, then mutate" is the property worth being able to
        // read off the method rather than infer from transaction semantics.
        UUID publishedSetId = UUID.randomUUID();
        List<PolicyParameter> figures = copyForward(outgoing, publishedSetId, changes);
        supersede(outgoing, details.effectiveFrom());

        PolicyParameterSet published = sets.save(new PolicyParameterSet(
                publishedSetId,
                outgoing.getProgramCode(),
                details.versionLabel(),
                details.effectiveFrom(),
                details.sourceCitation(),
                LocalDate.now(clock)));
        parameters.saveAll(figures);

        proposal.accept(reviewerName, clock.instant(), published.getId());
        auditService.append(AuditEventType.POLICY_PARAMETER_PUBLISHED, reviewerName, "POLICY_PARAMETER_SET",
                published.getId(), Map.of(
                        "proposalId", proposal.getId().toString(),
                        "versionLabel", details.versionLabel(),
                        "effectiveFrom", details.effectiveFrom().toString(),
                        "supersededVersionLabel", outgoing.getVersionLabel(),
                        "changedParameterCount", changes.size(),
                        "generationModel", proposal.getGenerationModel(),
                        "promptVersion", proposal.getPromptVersion()));
        return proposals.save(proposal);
    }

    /** Closes the outgoing set so the two ranges abut rather than overlap. */
    private void supersede(PolicyParameterSet outgoing, LocalDate newEffectiveFrom) {
        if (!newEffectiveFrom.isAfter(outgoing.getEffectiveFrom())) {
            throw new IllegalArgumentException("a superseding set must start after " + outgoing.getVersionLabel()
                    + " (" + outgoing.getEffectiveFrom() + "), not on or before it");
        }
        if (outgoing.getEffectiveTo() == null) {
            outgoing.closeAt(newEffectiveFrom.minusDays(1));
            sets.save(outgoing);
        } else if (!newEffectiveFrom.isAfter(outgoing.getEffectiveTo())) {
            // Already closed and the new range would overlap it. Refused rather than closed again: V15 permits
            // closing an open range, never moving a closed one.
            throw new IllegalArgumentException("a superseding set must start after " + outgoing.getVersionLabel()
                    + " ends (" + outgoing.getEffectiveTo() + ")");
        }
    }

    /**
     * Every figure from the outgoing set, with accepted changes applied over the top. A proposed change that
     * matches no existing figure is refused -- the copilot's scope is new *values* for figures that already
     * exist (design doc §2.3), and a set that quietly grew a parameter would resolve differently for reasons
     * nobody reviewed.
     */
    private List<PolicyParameter> copyForward(PolicyParameterSet outgoing, UUID newSetId,
            List<ProposedParameterValue> changes) {
        Map<String, BigDecimal> overrides = new LinkedHashMap<>();
        for (ProposedParameterValue change : changes) {
            validate(change);
            overrides.put(key(change.name(), change.householdSize()), change.newValue());
        }

        List<PolicyParameter> copied = new ArrayList<>();
        for (PolicyParameter existing :
                parameters.findByParameterSetIdOrderByNameAscHouseholdSizeAsc(outgoing.getId())) {
            BigDecimal value = overrides.remove(key(existing.getName(), existing.getHouseholdSize()));
            copied.add(existing.copyInto(newSetId, value != null ? value : existing.getNumericValue()));
        }
        if (!overrides.isEmpty()) {
            throw new IllegalArgumentException("proposal names figures that are not in "
                    + outgoing.getVersionLabel() + ": " + overrides.keySet());
        }
        return copied;
    }

    /**
     * The bounds a benefit figure cannot be outside of regardless of what any policy document says. Not a
     * judgement about whether a change is *right* -- that is the reviewer's, deliberately.
     */
    private static void validate(ProposedParameterValue change) {
        if (change.newValue() == null || change.newValue().signum() < 0) {
            throw new IllegalArgumentException(change.name() + " cannot be negative (got " + change.newValue() + ")");
        }
        if ("RATE".equals(change.unit()) && change.newValue().compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    change.name() + " is a fraction of 1, not a percentage (got " + change.newValue() + ")");
        }
        if ("COUNT".equals(change.unit()) && change.newValue().stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException(
                    change.name() + " must be a whole number (got " + change.newValue() + ")");
        }
    }

    private static String key(String name, Integer householdSize) {
        return name + "/" + householdSize;
    }

    private PolicyParameterSet requireSet(UUID parameterSetId) {
        return sets.findById(parameterSetId).orElseThrow(() ->
                new PolicyParameterNotFoundException("no published SNAP parameter set with id " + parameterSetId));
    }

    private PolicyParameterProposal requireProposal(UUID proposalId) {
        return proposals.findById(proposalId).orElseThrow(() ->
                new NoSuchElementException("no policy parameter proposal with id " + proposalId));
    }

    private String writeJson(List<ProposedParameterValue> values) {
        try {
            return objectMapper.writeValueAsString(values);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("could not serialize proposed values", e);
        }
    }

    private List<ProposedParameterValue> readJson(String json) {
        try {
            return objectMapper.readValue(json, PROPOSED_VALUES);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("could not read stored proposed values", e);
        }
    }

    /**
     * What a reviewer supplies when accepting. None of it can be derived: an effective date is a policy fact
     * stated by the memo, the citation is the memo itself, and {@code versionLabel} is unique by constraint.
     */
    public record PublicationDetails(String versionLabel, LocalDate effectiveFrom, String sourceCitation) {}
}
