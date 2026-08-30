package canopica.api.determination;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import canopica.api.domain.DeterminationTrace;
import canopica.api.domain.EligibilityDetermination;
import canopica.api.pgmq.PgmqService;
import canopica.api.policy.PolicyParameterResolver;
import canopica.api.repo.DeterminationTraceRepository;
import canopica.api.repo.EligibilityDeterminationRepository;
import canopica.rules.SnapDecision;
import canopica.rules.SnapDmnEvaluator;
import canopica.rules.SnapFacts;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
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
    private final AuditService auditService;
    private final PgmqService pgmq;

    JdbcDeterminationService(JdbcTemplate jdbc, FactAssembler factAssembler,
                              PolicyParameterResolver policyParameterResolver, SnapDmnEvaluator evaluator,
                              EligibilityDeterminationRepository determinations,
                              DeterminationTraceRepository traces, ObjectMapper objectMapper,
                              AuditService auditService, PgmqService pgmq) {
        this.jdbc = jdbc;
        this.factAssembler = factAssembler;
        this.policyParameterResolver = policyParameterResolver;
        this.evaluator = evaluator;
        this.determinations = determinations;
        this.traces = traces;
        this.objectMapper = objectMapper;
        this.auditService = auditService;
        this.pgmq = pgmq;
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

        Map<String, Object> auditPayload = new LinkedHashMap<>();
        auditPayload.put("eligible", decision.eligible());
        auditPayload.put("benefitAmount", decision.benefitAmount());
        auditPayload.put("reasonCode", decision.reasonCode());
        auditPayload.put("policyParameterVersion", parameters.parameterSetVersion());
        auditPayload.put("asOfDate", asOf.toString());
        auditService.append(AuditEventType.DETERMINATION_MADE, decidedBy,
                "eligibility_determination", determinationId, auditPayload);

        // Design doc §2.2's outbox guarantee, same pattern PgmqService's own doc comment already
        // establishes for DocumentService's document_intake enqueue: sharing this method's own
        // @Transactional connection means drafting correspondence can never fire for a determination
        // that ends up rolled back, and never silently fails to fire for one that commits. Drafting
        // itself never holds up this binding decision (constraint 17) -- it's a fire-and-forget
        // enqueue, not a call into ai/ from here.
        pgmq.send("correspondence_dispatch", Map.of("determination_id", determinationId.toString()));

        // Phase 4 Task 2, constraint 17 again: fraud-risk scoring shares this same transaction and
        // is just as much a fire-and-forget enqueue as correspondence above -- scoring never holds up
        // this binding decision, and never fires for a determination that ends up rolled back.
        pgmq.send("fraud_scoring", Map.of("determination_id", determinationId.toString()));

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
