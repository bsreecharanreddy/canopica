package ies.portal.caseload;

import ies.portal.domain.CaseAssignment;
import ies.portal.repo.CaseAssignmentRepository;
import ies.portal.repo.HouseholdRepository;
import java.time.Clock;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * {@code case_assignment} is the sole source of truth for "who can see this household" (design doc §2.1) --
 * never a role check, never a county match. Assignment is auto-claim-on-first-touch: the first worker to
 * open a household with no existing assignment becomes the assigned worker, with no separate
 * assignment-queue UI. A {@code SUPERVISOR} can always view any household (that check lives in
 * WorkerCaseController, not here) and can explicitly reassign one.
 */
@Service
public class CaseAssignmentService {

    private final CaseAssignmentRepository caseAssignments;
    private final HouseholdRepository households;
    private final Clock clock;

    public CaseAssignmentService(CaseAssignmentRepository caseAssignments, HouseholdRepository households, Clock clock) {
        this.caseAssignments = caseAssignments;
        this.households = households;
        this.clock = clock;
    }

    /**
     * No-op if an active assignment already exists, for whichever worker holds it -- the first claim
     * sticks, regardless of which worker views the household next. Returns the (possibly just-created)
     * active assignment; the caller compares its {@code workerId} to decide access.
     */
    @Transactional
    public CaseAssignment assignOnFirstTouch(UUID householdId, UUID workerId) {
        Optional<CaseAssignment> existing = activeAssignment(householdId);
        if (existing.isPresent()) {
            return existing.get();
        }
        return caseAssignments.save(
                new CaseAssignment(UUID.randomUUID(), householdId, workerId, LocalDate.now(clock), null));
    }

    /**
     * Ends any active assignment and starts a new one, effective-dated like everything else in this schema.
     * SUPERVISOR-only -- enforced by the caller (SupervisorController), not here.
     */
    @Transactional
    public CaseAssignment reassign(UUID householdId, UUID newWorkerId) {
        LocalDate today = LocalDate.now(clock);
        activeAssignment(householdId).ifPresent(current -> caseAssignments.endAssignment(current.getId(), today));
        return caseAssignments.save(new CaseAssignment(UUID.randomUUID(), householdId, newWorkerId, today, null));
    }

    /**
     * Sensitive-case flagging (design doc §2.1): flag-and-log, not sealing -- every role that could already
     * see the household still can, this only raises the audit signal. SUPERVISOR-only -- enforced by the
     * caller (SupervisorController), not here. Needs its own transaction the same reason reassign() does:
     * HouseholdRepository.updateSensitivity is a @Modifying query, which Spring Data JPA refuses to run
     * outside one.
     */
    @Transactional
    public void flagSensitivity(UUID householdId, boolean isSensitive, String reason) {
        households.updateSensitivity(householdId, isSensitive, reason);
    }

    /** True if {@code workerId} currently holds the active assignment for {@code householdId}. */
    public boolean isAssignedTo(UUID householdId, UUID workerId) {
        return activeAssignment(householdId).map(CaseAssignment::getWorkerId).map(workerId::equals).orElse(false);
    }

    private Optional<CaseAssignment> activeAssignment(UUID householdId) {
        List<CaseAssignment> active = caseAssignments.findEffectiveOn(householdId, LocalDate.now(clock));
        return active.stream().findFirst();
    }
}
