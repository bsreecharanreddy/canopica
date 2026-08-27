package canopica.api.intake;

import canopica.api.api.dto.IntakeExpenseDto;
import canopica.api.api.dto.IntakeIncomeDto;
import canopica.api.api.dto.IntakePersonDto;
import canopica.api.api.dto.IntakeRequest;
import canopica.api.api.dto.IntakeResourceDto;
import canopica.api.audit.AuditEventType;
import canopica.api.audit.AuditService;
import canopica.api.domain.Application;
import canopica.api.domain.ExpenseRecord;
import canopica.api.domain.Household;
import canopica.api.domain.HouseholdMember;
import canopica.api.domain.IncomeRecord;
import canopica.api.domain.LivingArrangement;
import canopica.api.domain.Person;
import canopica.api.domain.ProgramRequest;
import canopica.api.domain.ResourceRecord;
import canopica.api.domain.Verification;
import canopica.api.repo.ApplicationRepository;
import canopica.api.repo.ExpenseRecordRepository;
import canopica.api.repo.HouseholdMemberRepository;
import canopica.api.repo.HouseholdRepository;
import canopica.api.repo.IncomeRecordRepository;
import canopica.api.repo.LivingArrangementRepository;
import canopica.api.repo.PersonRepository;
import canopica.api.repo.ProgramRequestRepository;
import canopica.api.repo.ResourceRecordRepository;
import canopica.api.repo.VerificationRepository;
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

        int headIndex = findHeadOfHouseholdIndex(members);
        List<UUID> memberPersonIds = persistPersons(members, headIndex, actorId);
        UUID headPersonId = memberPersonIds.get(headIndex);

        UUID householdId = UUID.randomUUID();
        households.save(new Household(householdId, headPersonId, request.county(), request.addressLine1(),
                request.addressLine2(), request.city(), request.state(), request.zipCode()));

        persistHouseholdMembers(members, householdId, memberPersonIds, today);

        livingArrangements.save(new LivingArrangement(UUID.randomUUID(), householdId, request.arrangementType(),
                request.paysUtilitiesSeparatelyOrDefault(), today, null));

        persistIncomeAndExpenses(members, memberPersonIds);
        persistResources(request.resources(), householdId);

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

    private static int findHeadOfHouseholdIndex(List<IntakePersonDto> members) {
        for (int i = 0; i < members.size(); i++) {
            if ("SELF".equals(members.get(i).relationship())) {
                return i;
            }
        }
        throw new InvalidIntakeException("household must include exactly one member with relationship SELF");
    }

    private List<UUID> persistPersons(List<IntakePersonDto> members, int headIndex, String actorId) {
        List<UUID> memberPersonIds = new ArrayList<>(members.size());
        for (int i = 0; i < members.size(); i++) {
            IntakePersonDto member = members.get(i);
            UUID personId = UUID.randomUUID();
            // Only the head's row carries the submitter's identity -- see Person.keycloakSubject's own
            // javadoc for why the other members' rows stay unlinked.
            String keycloakSubject = i == headIndex ? actorId : null;
            persons.save(new Person(personId, member.firstName(), member.lastName(), member.dateOfBirth(),
                    "tok-" + personId, member.sex(), member.isUsCitizenOrDefault(), keycloakSubject));
            memberPersonIds.add(personId);
        }
        return memberPersonIds;
    }

    private void persistHouseholdMembers(List<IntakePersonDto> members, UUID householdId,
            List<UUID> memberPersonIds, LocalDate today) {
        for (int i = 0; i < members.size(); i++) {
            IntakePersonDto member = members.get(i);
            householdMembers.save(new HouseholdMember(UUID.randomUUID(), householdId, memberPersonIds.get(i),
                    member.relationship(), member.purchasesAndPreparesFoodTogetherOrDefault(), today, null));
        }
    }

    private void persistIncomeAndExpenses(List<IntakePersonDto> members, List<UUID> memberPersonIds) {
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
    }

    private void persistResources(List<IntakeResourceDto> resources, UUID householdId) {
        for (IntakeResourceDto resource : resources) {
            resourceRecords.save(new ResourceRecord(UUID.randomUUID(), householdId, resource.resourceType(),
                    resource.amount(), resource.effectiveFrom(), resource.effectiveTo()));
        }
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
