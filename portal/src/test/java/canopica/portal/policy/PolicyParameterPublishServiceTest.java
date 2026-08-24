package canopica.portal.policy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.portal.AbstractPostgresTest;
import canopica.portal.domain.PolicyParameterProposal;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * The publish path -- the only code in this system that writes the dollar figures a determination resolves
 * against. Driven against a real Postgres with the real migrations and the real seeded FY2026 parameter set;
 * only the copilot itself is stubbed, so that a staged proposal is exact and repeatable. What the model
 * actually produces from a policy memo is tested against a real model, in
 * {@code ai/tests/test_rule_authoring.py}.
 *
 * <p>{@code @Transactional} because accepting a proposal closes the seeded FY2026 set: without a rollback
 * that would leak into every other test sharing this JVM's singleton container.
 */
@Import(PolicyParameterPublishServiceTest.StubCopilotConfiguration.class)
@Transactional
class PolicyParameterPublishServiceTest extends AbstractPostgresTest {

    /** The open-ended set V4 seeds, and the one a Task 3 proposal realistically supersedes. */
    private static final UUID FY2026 = UUID.fromString("9f1c0e10-0000-4000-8000-000000000002");

    private static final PolicyParameterPublishService.PublicationDetails FY2027 =
            new PolicyParameterPublishService.PublicationDetails(
                    "SNAP-FY2027", LocalDate.of(2026, 10, 1), "FY2027 COLA memo, USDA FNS");

    @Autowired PolicyParameterPublishService service;
    @Autowired StubCopilot copilot;
    @Autowired PolicyParameterResolver resolver;
    @Autowired JdbcTemplate jdbc;

    @PersistenceContext EntityManager entityManager;

    @BeforeEach
    void resetStub() {
        copilot.reset();
    }

    /**
     * Reads the column with raw SQL, not through JPA, so the assertion is about what is in the database
     * rather than what is in the persistence context -- which is the whole question for a column V15 only
     * just made writable at all. The flush is what makes that possible: inside this class's rollback-only
     * transaction, a dirty entity would otherwise never reach Postgres, and asserting "still null" would pass
     * for the wrong reason.
     */
    private LocalDate effectiveToOf(UUID parameterSetId) {
        entityManager.flush();
        return jdbc.queryForObject(
                "select effective_to from policy_parameter_set where id = ?", LocalDate.class, parameterSetId);
    }

    private PolicyParameterProposal proposalFor(ProposedParameterValue... changes) {
        copilot.stage(List.of(changes));
        return service.propose("FY2027 COLA memo text", FY2026, "admin.alex");
    }

    private static ProposedParameterValue change(String name, Integer size, String from, String to, String unit) {
        return new ProposedParameterValue(
                name, size, new BigDecimal(from), new BigDecimal(to), unit, "stated by the memo");
    }

    @Test
    void aProposalIsPersistedAsPendingWithItsProvenance() {
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        assertThat(proposal.getStatus()).isEqualTo(PolicyParameterProposal.Status.PENDING);
        assertThat(proposal.getProposedBy()).isEqualTo("admin.alex");
        assertThat(proposal.getReviewedBy()).isNull();
        assertThat(proposal.getPublishedParameterSetId()).isNull();
        // "An AI proposed it" is never a complete answer to who changed a benefit figure, but it is part of
        // the answer, and it has to survive on the row.
        assertThat(proposal.getGenerationModel()).isEqualTo("llama3.2:3b");
        assertThat(proposal.getPromptVersion()).isEqualTo("v1");
    }

    @Test
    void theCopilotIsShownEveryFigureCurrentlyInForce() {
        // The scope guarantee runs both ways: the copilot may only propose changes to figures in this list,
        // so a truncated list would silently narrow what it is allowed to read a memo as saying.
        proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        assertThat(copilot.lastCurrentValues)
                .extracting(CurrentParameterValue::name)
                .contains("MAX_ALLOTMENT", "STANDARD_DEDUCTION", "GROSS_INCOME_LIMIT", "NET_INCOME_LIMIT",
                        "EARNED_INCOME_DEDUCTION_RATE", "MINIMUM_BENEFIT");
    }

    @Test
    void acceptingPublishesASetTheResolverActuallyResolvesTo() {
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        service.accept(proposal.getId(), "admin.alex", FY2027);

        var resolved = resolver.resolveSnap(LocalDate.of(2026, 10, 1), 1);
        assertThat(resolved.parameterSetVersion()).isEqualTo("SNAP-FY2027");
        assertThat(resolved.maxAllotment()).isEqualByComparingTo("305");
    }

    @Test
    void thePublishedSetIsCompleteNotJustTheChangedFigures() {
        // PolicyParameterResolver needs the whole parameter list to build a SnapPolicyParameters; a set
        // carrying only the diff would fail to resolve at all, on the next determination rather than here.
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        service.accept(proposal.getId(), "admin.alex", FY2027);

        var before = resolver.resolveSnap(LocalDate.of(2026, 9, 30), 4);
        var after = resolver.resolveSnap(LocalDate.of(2026, 10, 1), 4);
        assertThat(after.standardDeduction()).isEqualByComparingTo(before.standardDeduction());
        assertThat(after.earnedIncomeDeductionRate()).isEqualByComparingTo(before.earnedIncomeDeductionRate());
        assertThat(after.minimumBenefit()).isEqualByComparingTo(before.minimumBenefit());
    }

    @Test
    void theSupersededSetIsClosedSoTheRangesAbutRatherThanOverlap() {
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        service.accept(proposal.getId(), "admin.alex", FY2027);

        // The real failure this prevents is not cosmetic: two sets covering one date makes findEffectiveOn
        // return two rows into an Optional, which surfaces as a failed *determination* long after the publish.
        assertThat(effectiveToOf(FY2026)).isEqualTo(LocalDate.of(2026, 9, 30));
        assertThat(resolver.resolveSnap(LocalDate.of(2026, 9, 30), 1).parameterSetVersion())
                .isEqualTo("SNAP-FY2026");
    }

    @Test
    void anEarlierDeterminationStillReproducesAgainstItsOwnParameterSet() {
        // The whole reason V15's narrowing is safe (see docs/design/2026-08-23-policy-parameter-supersession.md):
        // re-derivation resolves by parameter-set id and never reads either date column, so closing FY2026
        // cannot change what a determination made under it reproduces to.
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        service.accept(proposal.getId(), "admin.alex", FY2027);

        assertThat(resolver.resolveSnapByParameterSetId(FY2026, 1).maxAllotment())
                .isEqualByComparingTo("298");
    }

    @Test
    void acceptingRecordsTheReviewerOnTheProposalAndInTheAuditChain() {
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        PolicyParameterProposal reviewed = service.accept(proposal.getId(), "admin.alex", FY2027);

        assertThat(reviewed.getStatus()).isEqualTo(PolicyParameterProposal.Status.ACCEPTED);
        assertThat(reviewed.getReviewedBy()).isEqualTo("admin.alex");
        assertThat(reviewed.getReviewedAt()).isNotNull();
        assertThat(reviewed.getPublishedParameterSetId()).isNotNull();
        // The proposal row above is mutable by design, so it cannot be the tamper-evident answer to "who put
        // this figure in force". The chain can.
        Integer chained = jdbc.queryForObject(
                "select count(*) from audit_event where event_type = 'POLICY_PARAMETER_PUBLISHED' "
                        + "and actor_id = 'admin.alex' and subject_id = ?",
                Integer.class, reviewed.getPublishedParameterSetId());
        assertThat(chained).isEqualTo(1);
    }

    @Test
    void rejectingLeavesTheEffectiveSetExactlyAsItWas() {
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));

        PolicyParameterProposal reviewed = service.reject(proposal.getId(), "admin.alex");

        assertThat(reviewed.getStatus()).isEqualTo(PolicyParameterProposal.Status.REJECTED);
        assertThat(reviewed.getReviewedBy()).isEqualTo("admin.alex");
        assertThat(reviewed.getPublishedParameterSetId()).isNull();
        assertThat(resolver.resolveSnap(LocalDate.of(2026, 10, 1), 1).parameterSetVersion())
                .isEqualTo("SNAP-FY2026");
        assertThat(effectiveToOf(FY2026)).isNull();
    }

    @Test
    void anAlreadyReviewedProposalCannotBeReviewedAgain() {
        // Without this, a second accept would publish a second parameter set from one human decision.
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));
        service.reject(proposal.getId(), "admin.alex");

        assertThatThrownBy(() -> service.accept(proposal.getId(), "admin.alex", FY2027))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("already reviewed");
    }

    @Test
    void aNegativeDollarAmountIsRefusedBeforeItReachesTheDatabase() {
        // Asserted as a delta, not an absolute count: PolicyParameterProposalControllerTest commits its own
        // rows into this JVM's shared container, so "the table is empty" is only true when this class runs
        // alone -- and a test that passes alone but not in the suite is worse than no test.
        long before = proposalCount();

        assertThatThrownBy(() -> proposalFor(change("MAX_ALLOTMENT", 1, "298", "-5", "USD_PER_MONTH")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("cannot be negative");

        assertThat(proposalCount()).isEqualTo(before);
    }

    private long proposalCount() {
        Long count = jdbc.queryForObject("select count(*) from policy_parameter_proposal", Long.class);
        return count == null ? 0 : count;
    }

    @Test
    void aRateAboveOneIsRefused() {
        // 20 rather than 0.20 is the realistic version of this mistake: a memo says "20 percent", and a
        // fivefold error in the earned-income deduction is not obviously wrong on a review screen.
        assertThatThrownBy(() ->
                proposalFor(change("EARNED_INCOME_DEDUCTION_RATE", null, "0.20", "20", "RATE")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("fraction of 1");
    }

    @Test
    void aFigureThatIsNotInTheSupersededSetIsRefused() {
        // The copilot's scope is new values for figures that already exist. A set that quietly grew a
        // parameter would resolve differently for a reason nobody reviewed.
        PolicyParameterProposal proposal =
                proposalFor(change("TELEWORK_ALLOWANCE", 1, "0", "50", "USD_PER_MONTH"));

        assertThatThrownBy(() -> service.accept(proposal.getId(), "admin.alex", FY2027))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("TELEWORK_ALLOWANCE");
    }

    @Test
    void aSupersedingSetCannotStartOnOrBeforeTheSetItSupersedes() {
        PolicyParameterProposal proposal =
                proposalFor(change("MAX_ALLOTMENT", 1, "298", "305", "USD_PER_MONTH"));
        var overlapping = new PolicyParameterPublishService.PublicationDetails(
                "SNAP-BACKDATED", LocalDate.of(2025, 10, 1), "backdated");

        assertThatThrownBy(() -> service.accept(proposal.getId(), "admin.alex", overlapping))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("must start after");
    }

    /**
     * A hand-written stub rather than a mock: it records what it was asked and returns what a test staged,
     * which is all this suite needs, and it stays readable as a plain class.
     */
    static class StubCopilot implements RuleAuthoringClient {

        private final Deque<List<ProposedParameterValue>> staged = new ArrayDeque<>();
        List<CurrentParameterValue> lastCurrentValues = List.of();

        void stage(List<ProposedParameterValue> changes) {
            staged.add(changes);
        }

        void reset() {
            staged.clear();
            lastCurrentValues = List.of();
        }

        @Override
        public ParameterProposalDraft propose(String documentExcerpt, UUID currentParameterSetId,
                List<CurrentParameterValue> currentValues) {
            lastCurrentValues = new ArrayList<>(currentValues);
            List<ProposedParameterValue> changes = staged.poll();
            if (changes == null) {
                throw new AssertionError("copilot called without a staged proposal");
            }
            return new ParameterProposalDraft(
                    currentParameterSetId, changes, documentExcerpt, "llama3.2:3b", "v1");
        }
    }

    @TestConfiguration
    static class StubCopilotConfiguration {

        @Bean
        @Primary
        StubCopilot stubCopilot() {
            return new StubCopilot();
        }
    }
}
