package ies.portal.intake;

import ies.portal.api.dto.IntakeExpenseDto;
import ies.portal.api.dto.IntakeIncomeDto;
import ies.portal.api.dto.IntakePersonDto;
import ies.portal.api.dto.IntakeRequest;
import ies.portal.audit.AuditEventType;
import ies.portal.audit.AuditService;
import ies.portal.domain.Application;
import ies.portal.domain.ExpenseRecord;
import ies.portal.domain.Household;
import ies.portal.domain.HouseholdMember;
import ies.portal.domain.IncomeRecord;
import ies.portal.domain.LivingArrangement;
import ies.portal.domain.Person;
import ies.portal.domain.ProgramRequest;
import ies.portal.repo.ApplicationRepository;
import ies.portal.repo.ExpenseRecordRepository;
import ies.portal.repo.HouseholdMemberRepository;
import ies.portal.repo.HouseholdRepository;
import ies.portal.repo.IncomeRecordRepository;
import ies.portal.repo.LivingArrangementRepository;
import ies.portal.repo.PersonRepository;
import ies.portal.repo.ProgramRequestRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Writes an intake submission -- person(s), household, household_member(s), living_arrangement,
 * income/expense records, application, program_request -- in one transaction, then appends the
 * {@code APPLICATION_SUBMITTED} audit event. Only SNAP is requested; Phase 1a supports no other program.
 */
@Service
public class IntakeService {

    private final PersonRepository persons;
    private final HouseholdRepository households;
    private final HouseholdMemberRepository householdMembers;
    private final LivingArrangementRepository livingArrangements;
    private final IncomeRecordRepository incomeRecords;
    private final ExpenseRecordRepository expenseRecords;
    private final ApplicationRepository applications;
    private final ProgramRequestRepository programRequests;
    private final AuditService auditService;
    private final Clock clock;

    IntakeService(PersonRepository persons, HouseholdRepository households,
                  HouseholdMemberRepository householdMembers, LivingArrangementRepository livingArrangements,
                  IncomeRecordRepository incomeRecords, ExpenseRecordRepository expenseRecords,
                  ApplicationRepository applications, ProgramRequestRepository programRequests,
                  AuditService auditService, Clock clock) {
        this.persons = persons;
        this.households = households;
        this.householdMembers = householdMembers;
        this.livingArrangements = livingArrangements;
        this.incomeRecords = incomeRecords;
        this.expenseRecords = expenseRecords;
        this.applications = applications;
        this.programRequests = programRequests;
        this.auditService = auditService;
        this.clock = clock;
    }

    @Transactional
    public IntakeResult submit(IntakeRequest request, String actorId) {
        LocalDate today = LocalDate.now(clock);
        List<IntakePersonDto> members = request.members();

        int headIndex = -1;
        for (int i = 0; i < members.size(); i++) {
            if ("SELF".equals(members.get(i).relationship())) {
                headIndex = i;
                break;
            }
        }
        if (headIndex < 0) {
            throw new InvalidIntakeException("household must include exactly one member with relationship SELF");
        }

        List<UUID> memberPersonIds = new ArrayList<>(members.size());
        for (IntakePersonDto member : members) {
            UUID personId = UUID.randomUUID();
            persons.save(new Person(personId, member.firstName(), member.lastName(), member.dateOfBirth(),
                    "tok-" + personId, member.sex(), member.isUsCitizenOrDefault()));
            memberPersonIds.add(personId);
        }
        UUID headPersonId = memberPersonIds.get(headIndex);

        UUID householdId = UUID.randomUUID();
        households.save(new Household(householdId, headPersonId, request.county(), request.addressLine1(),
                request.addressLine2(), request.city(), request.state(), request.zipCode()));

        for (int i = 0; i < members.size(); i++) {
            IntakePersonDto member = members.get(i);
            householdMembers.save(new HouseholdMember(UUID.randomUUID(), householdId, memberPersonIds.get(i),
                    member.relationship(), member.purchasesAndPreparesFoodTogetherOrDefault(), today, null));
        }

        livingArrangements.save(new LivingArrangement(UUID.randomUUID(), householdId, request.arrangementType(),
                request.paysUtilitiesSeparatelyOrDefault(), today, null));

        for (int i = 0; i < members.size(); i++) {
            UUID personId = memberPersonIds.get(i);
            for (IntakeIncomeDto income : members.get(i).incomes()) {
                incomeRecords.save(new IncomeRecord(UUID.randomUUID(), personId, income.incomeType(),
                        income.earned(), income.monthlyAmount(), income.effectiveFrom(), income.effectiveTo()));
            }
            for (IntakeExpenseDto expense : members.get(i).expenses()) {
                expenseRecords.save(new ExpenseRecord(UUID.randomUUID(), personId, expense.expenseType(),
                        expense.monthlyAmount(), expense.effectiveFrom(), expense.effectiveTo()));
            }
        }

        UUID applicationId = UUID.randomUUID();
        applications.save(new Application(applicationId, householdId, Instant.now(clock), request.channelOrDefault()));

        UUID programRequestId = UUID.randomUUID();
        programRequests.save(new ProgramRequest(
                programRequestId, applicationId, "SNAP", "SUBMITTED", today, false));

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("householdId", householdId.toString());
        payload.put("applicationId", applicationId.toString());
        auditService.append(AuditEventType.APPLICATION_SUBMITTED, actorId,
                "program_request", programRequestId, payload);

        return new IntakeResult(applicationId, programRequestId);
    }
}
