package ies.portal.determination;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import ies.portal.domain.DeterminationTrace;
import ies.portal.domain.EligibilityDetermination;
import ies.portal.policy.PolicyParameterResolver;
import ies.portal.repo.DeterminationTraceRepository;
import ies.portal.repo.EligibilityDeterminationRepository;
import ies.rules.SnapDecision;
import ies.rules.SnapDmnEvaluator;
import ies.rules.SnapFacts;
import java.time.LocalDate;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Assembles facts as of a decision date, resolves the parameter set as of
 * the same date, evaluates the DMN model, and writes an append-only
 * {@code eligibility_determination} plus its complete
 * {@code determination_trace}. See {@link SnapDmnEvaluator}'s doc comment
 * for why replaying the same two inputs always reproduces the same
 * {@link SnapDecision}.
 */
@Service
class JdbcDeterminationService implements DeterminationService {

    private final JdbcTemplate jdbc;
    private final FactAssembler factAssembler;
    private final PolicyParameterResolver policyParameterResolver;
    private final SnapDmnEvaluator evaluator;
    private final EligibilityDeterminationRepository determinations;
    private final DeterminationTraceRepository traces;
    private final ObjectMapper objectMapper;

    JdbcDeterminationService(JdbcTemplate jdbc, FactAssembler factAssembler,
                              PolicyParameterResolver policyParameterResolver, SnapDmnEvaluator evaluator,
                              EligibilityDeterminationRepository determinations,
                              DeterminationTraceRepository traces, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.factAssembler = factAssembler;
        this.policyParameterResolver = policyParameterResolver;
        this.evaluator = evaluator;
        this.determinations = determinations;
        this.traces = traces;
        this.objectMapper = objectMapper;
    }

    @Override
    @Transactional
    public UUID determine(UUID programRequestId, LocalDate asOf, LocalDate benefitMonth, String decidedBy) {
        UUID householdId = findHouseholdId(programRequestId);

        SnapFacts facts = factAssembler.assemble(householdId, asOf);
        var parameters = policyParameterResolver.resolveSnap(asOf, facts.householdSize());
        SnapDecision decision = evaluator.evaluate(facts, parameters);

        UUID determinationId = UUID.randomUUID();
        determinations.save(new EligibilityDetermination(
                determinationId, programRequestId, benefitMonth, asOf,
                decision.eligible(), decision.benefitAmount(), decision.reasonCode(),
                parameters.parameterSetId(), parameters.parameterSetVersion(), decidedBy));

        traces.save(new DeterminationTrace(
                UUID.randomUUID(), determinationId,
                writeJson(facts), writeJson(decision.trace()),
                "snap-eligibility", evaluator.modelHash(), SnapDmnEvaluator.ENGINE_VERSION));

        return determinationId;
    }

    @Override
    public SnapDecision reproduce(UUID determinationId) {
        EligibilityDetermination determination = determinations.findById(determinationId)
                .orElseThrow(() -> new NoSuchElementException("no eligibility_determination with id " + determinationId));
        DeterminationTrace trace = traces.findByDeterminationId(determinationId)
                .orElseThrow(() -> new NoSuchElementException("no determination_trace for determination " + determinationId));

        SnapFacts facts = readJson(trace.getInputSnapshot(), SnapFacts.class);
        var parameters = policyParameterResolver.resolveSnapByParameterSetId(
                determination.getPolicyParameterSetId(), facts.householdSize());

        return evaluator.evaluate(facts, parameters);
    }

    private UUID findHouseholdId(UUID programRequestId) {
        return jdbc.queryForObject(
                """
                select a.household_id from program_request r
                join application a on a.id = r.application_id
                where r.id = ?
                """,
                (rs, rowNum) -> (UUID) rs.getObject("household_id"),
                programRequestId);
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to serialize determination trace data", e);
        }
    }

    private <T> T readJson(String json, Class<T> type) {
        try {
            return objectMapper.readValue(json, type);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to deserialize stored input snapshot", e);
        }
    }
}
