package canopica.portal.verification;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.portal.audit.AuditEventType;
import canopica.portal.audit.AuditService;
import canopica.portal.domain.Verification;
import canopica.portal.domain.VerificationResponse;
import canopica.portal.repo.ApplicationRepository;
import canopica.portal.repo.HouseholdRepository;
import canopica.portal.repo.ProgramRequestRepository;
import canopica.portal.repo.VerificationRepository;
import canopica.portal.repo.VerificationResponseRepository;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * The mocked external-verification counterparty (design doc §2.2). Synchronous REST rather than the
 * batch/SFTP shape a real interface would use (tradeoffs doc, Interfaces tier "Transport" row) -- there's
 * nothing to actually wait on, so a request resolves in the same call. The mock is deterministic: the same
 * (person, data element) pair always maps to the same outcome, the same reproducibility property the DMN
 * model already holds for determinations.
 *
 * <p>FTI-style safeguards (design doc §2.2, made concrete): every request and its resolution is its own
 * {@code VERIFICATION_UPDATED} audit-chain event, not just a log line -- appended as two events
 * ({@code REQUESTED} then {@code RECEIVED}) even though both happen within this one call, so the audit
 * trail reads the same shape a real async interface would produce.
 */
@Service
public class MockVerificationService {

    private static final List<String> OUTCOMES = List.of("MATCHES", "DISCREPANCY", "UNAVAILABLE");

    private final VerificationRepository verifications;
    private final VerificationResponseRepository verificationResponses;
    private final ProgramRequestRepository programRequests;
    private final ApplicationRepository applications;
    private final HouseholdRepository households;
    private final AuditService auditService;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    MockVerificationService(VerificationRepository verifications, VerificationResponseRepository verificationResponses,
            ProgramRequestRepository programRequests, ApplicationRepository applications,
            HouseholdRepository households, AuditService auditService, ObjectMapper objectMapper, Clock clock) {
        this.verifications = verifications;
        this.verificationResponses = verificationResponses;
        this.programRequests = programRequests;
        this.applications = applications;
        this.households = households;
        this.auditService = auditService;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    /**
     * Requests and immediately resolves {@code verificationId}: writes a {@code verification_response},
     * moves {@code verification.status} to {@code RECEIVED}, and appends the REQUESTED/RECEIVED audit
     * pair. Returns the new response's id; the caller re-reads current state for the HTTP response, same
     * pattern {@code DeterminationController} uses around {@code determinationService.determine(...)}.
     */
    @Transactional
    public UUID requestVerification(UUID verificationId, String actorId) {
        Verification verification = verifications.findById(verificationId)
                .orElseThrow(() -> new NoSuchElementException("no verification with id " + verificationId));

        Map<String, Object> requested = new LinkedHashMap<>();
        requested.put("stage", "REQUESTED");
        requested.put("dataElement", verification.getDataElement());
        auditService.append(AuditEventType.VERIFICATION_UPDATED, actorId, "verification", verificationId, requested);

        UUID personId = applicantPersonId(verification.getProgramRequestId());
        String outcome = resolveOutcome(personId, verification.getDataElement());

        UUID responseId = UUID.randomUUID();
        verificationResponses.save(new VerificationResponse(
                responseId, verificationId, outcome, mockPayload(verification.getDataElement(), outcome)));
        verifications.updateStatus(verificationId, "RECEIVED", LocalDate.now(clock));

        Map<String, Object> received = new LinkedHashMap<>();
        received.put("stage", "RECEIVED");
        received.put("outcome", outcome);
        auditService.append(AuditEventType.VERIFICATION_UPDATED, actorId, "verification", verificationId, received);

        return responseId;
    }

    /**
     * Deterministic: hashes {@code (personId, dataElement)} via a name-based UUID (a pure function of the
     * input bytes, stable across JVM restarts) so reruns against the same synthetic data always land on
     * the same outcome.
     */
    public String resolveOutcome(UUID personId, String dataElement) {
        UUID digest = UUID.nameUUIDFromBytes((personId + ":" + dataElement).getBytes(StandardCharsets.UTF_8));
        int bucket = (int) Math.floorMod(digest.getLeastSignificantBits(), (long) OUTCOMES.size());
        return OUTCOMES.get(bucket);
    }

    private UUID applicantPersonId(UUID programRequestId) {
        UUID applicationId = programRequests.findById(programRequestId).orElseThrow().getApplicationId();
        UUID householdId = applications.findById(applicationId).orElseThrow().getHouseholdId();
        return households.findById(householdId).orElseThrow().getHeadPersonId();
    }

    private String mockPayload(String dataElement, String outcome) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("source", "MOCK_EXTERNAL_VERIFICATION_SERVICE");
        payload.put("dataElement", dataElement);
        payload.put("outcome", outcome);
        payload.put("resolvedAt", Instant.now(clock).toString());
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to serialize mock verification payload", e);
        }
    }
}
