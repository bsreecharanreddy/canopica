package canopica.portal.intake;

import canopica.portal.api.dto.IntakeExpenseDto;
import canopica.portal.api.dto.IntakeIncomeDto;
import canopica.portal.api.dto.IntakePersonDto;
import canopica.portal.api.dto.IntakeRequest;
import canopica.portal.api.dto.IntakeResourceDto;
import canopica.portal.audit.AuditEventType;
import canopica.portal.audit.AuditService;
import canopica.portal.domain.Application;
import canopica.portal.domain.ExpenseRecord;
import canopica.portal.domain.Household;
import canopica.portal.domain.HouseholdMember;
import canopica.portal.domain.IncomeRecord;
import canopica.portal.domain.LivingArrangement;
import canopica.portal.domain.Person;
import canopica.portal.domain.ProgramRequest;
import canopica.portal.domain.ResourceRecord;
import canopica.portal.domain.Verification;
import canopica.portal.repo.ApplicationRepository;
import canopica.portal.repo.ExpenseRecordRepository;
import canopica.portal.repo.HouseholdMemberRepository;
import canopica.portal.repo.HouseholdRepository;
import canopica.portal.repo.IncomeRecordRepository;
import canopica.portal.repo.LivingArrangementRepository;
import canopica.portal.repo.PersonRepository;
import canopica.portal.repo.ProgramRequestRepository;
import canopica.portal.repo.ResourceRecordRepository;
import canopica.portal.repo.VerificationRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
    private final ResourceRecordRepository resourceRecords;
    private final ApplicationRepository applications;
    private final ProgramRequestRepository programRequests;
    private final VerificationRepository verifications;
    private final AuditService auditService;
    private final Clock clock;

    // 7 CFR 273.2(i)(1)(iii)'s "rent or mortgage and utility expenses" leg --
    // FactAssembler's own shelterCost/utilityCost split (RENT_OR_MORTGAGE/
    // PROPERTY_TAX/HOME_INSURANCE vs. UTILITIES) is for the DMN's shelter
    // deduction; the expedited-processing test in the regulation bundles
    // rent/mortgage and utilities together, so this list is deliberately
    // broader than either of FactAssembler's two individual buckets.
    private static final Set<String> SHELTER_EXPENSE_TYPES =
            Set.of("RENT_OR_MORTGAGE", "PROPERTY_TAX", "HOME_INSURANCE", "UTILITIES");

    IntakeService(PersonRepository persons, HouseholdRepository households,
                  HouseholdMemberRepository householdMembers, LivingArrangementRepository livingArrangements,
                  IncomeRecordRepository incomeRecords, ExpenseRecordRepository expenseRecords,
                  ResourceRecordRepository resourceRecords,
                  ApplicationRepository applications, ProgramRequestRepository programRequests,
                  VerificationRepository verifications, AuditService auditService, Clock clock) {
        this.persons = persons;
        this.households = households;
        this.householdMembers = householdMembers;
        this.livingArrangements = livingArrangements;
        this.incomeRecords = incomeRecords;
        this.expenseRecords = expenseRecords;
        this.resourceRecords = resourceRecords;
        this.applications = applications;
        this.programRequests = programRequests;
        this.verifications = verifications;
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

        for (IntakeResourceDto resource : request.resources()) {
            resourceRecords.save(new ResourceRecord(UUID.randomUUID(), householdId, resource.resourceType(),
                    resource.amount(), resource.effectiveFrom(), resource.effectiveTo()));
        }

        boolean expedited = isExpedited(request);

        UUID applicationId = UUID.randomUUID();
        applications.save(new Application(applicationId, householdId, Instant.now(clock), request.channelOrDefault()));

        UUID programRequestId = UUID.randomUUID();
        programRequests.save(new ProgramRequest(
                programRequestId, applicationId, "SNAP", "SUBMITTED", today, expedited));

        // 7 CFR 273.2(f)(1): households must be given at least 10 days to provide verification. Only
        // INCOME is requested at intake today (design doc §2.2) -- the other data_element values the
        // verification table's CHECK constraint allows are for a later phase.
        verifications.save(new Verification(
                UUID.randomUUID(), programRequestId, "INCOME", "OUTSTANDING", today.plusDays(10), null));

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("householdId", householdId.toString());
        payload.put("applicationId", applicationId.toString());
        auditService.append(AuditEventType.APPLICATION_SUBMITTED, actorId,
                "program_request", programRequestId, payload);

        return new IntakeResult(applicationId, programRequestId);
    }

    /**
     * Computed directly from the just-submitted request, not a re-query of what
     * was just persisted -- every income/expense/resource on this submission is
     * "as of now" by construction, so there is nothing an effective-dated
     * as-of query would filter out that summing the request itself doesn't
     * already give.
     */
    private static boolean isExpedited(IntakeRequest request) {
        BigDecimal grossMonthlyIncome = request.members().stream()
                .flatMap(member -> member.incomes().stream())
                .map(IntakeIncomeDto::monthlyAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal shelterCost = request.members().stream()
                .flatMap(member -> member.expenses().stream())
                .filter(expense -> SHELTER_EXPENSE_TYPES.contains(expense.expenseType()))
                .map(IntakeExpenseDto::monthlyAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal liquidResources = request.resources().stream()
                .map(IntakeResourceDto::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return ExpeditedEligibility.isExpedited(grossMonthlyIncome, liquidResources, shelterCost);
    }
}
