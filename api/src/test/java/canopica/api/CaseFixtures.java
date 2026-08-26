package canopica.api;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Builds a household with members, income, and expenses directly in the
 * database (bypassing the not-yet-built intake API, which arrives in Task
 * 7) and returns its ids. Shared by every test from Task 5 onward that
 * needs a real, effective-dated case to evaluate a determination against.
 */
public final class CaseFixtures {

    /** The base effective date every fixture's records start from. */
    public static final LocalDate BASE_EFFECTIVE_FROM = LocalDate.of(2025, 1, 1);

    private CaseFixtures() {
    }

    /**
     * The exact household rules-engine's {@code SnapDmnEvaluatorTest} scenario
     * "three-person working household, capped shelter deduction" describes:
     * household size 3, one wage earner at $1,500/mo, rent $800 + utilities
     * $300. Expected FY2025 result: eligible, $649, ELIGIBLE.
     */
    public static Ids threePersonWorkingHousehold(JdbcTemplate jdbc) {
        UUID headId = insertPerson(jdbc, "Dana", "Reyes", LocalDate.of(1990, 4, 2));
        UUID spouseId = insertPerson(jdbc, "Alex", "Reyes", LocalDate.of(1991, 6, 15));
        UUID childId = insertPerson(jdbc, "Sam", "Reyes", LocalDate.of(2015, 9, 20));

        UUID householdId = insertHousehold(jdbc, headId);
        insertHouseholdMember(jdbc, householdId, headId, "SELF");
        insertHouseholdMember(jdbc, householdId, spouseId, "SPOUSE");
        insertHouseholdMember(jdbc, householdId, childId, "CHILD");

        insertIncome(jdbc, headId, "WAGES", true, "1500.00");
        insertExpense(jdbc, headId, "RENT_OR_MORTGAGE", "800.00");
        insertExpense(jdbc, headId, "UTILITIES", "300.00");
        insertLivingArrangement(jdbc, householdId, "RENTS");

        UUID programRequestId = insertApplicationAndRequest(jdbc, householdId);

        return new Ids(householdId, headId, programRequestId);
    }

    /** Reports a new income record effective from the given date, without ending the earlier one. */
    public static void reportIncomeChange(JdbcTemplate jdbc, Ids ids, String monthlyAmount, LocalDate effectiveFrom) {
        insertIncome(jdbc, ids.headPersonId(), "WAGES", true, monthlyAmount, effectiveFrom);
    }

    /** A bare {@code worker} row with a fabricated (non-Keycloak-backed) id -- for tests below the API layer. */
    public static UUID insertWorker(JdbcTemplate jdbc, String fullName, String role) {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into worker (id, full_name, email, role) values (?, ?, ?, ?)",
                id, fullName, "worker-" + id + "@canopica.local", role);
        return id;
    }

    /**
     * A {@code case_assignment} row, already active as of "today" under any interpretation of "today" --
     * {@code effective_from} is {@link #BASE_EFFECTIVE_FROM} (a fixed past date), not SQL's {@code
     * current_date}. Tests that seeded a pre-existing assignment with raw {@code current_date} intermittently
     * failed on CI: Postgres evaluates {@code current_date} in the container's own (UTC) timezone, while the
     * application's own {@code CaseAssignmentService} always compares against {@code LocalDate.now(clock)}
     * using {@code canopica.timezone=America/New_York} (application.yml) -- during the ~4-6 hours every day where
     * UTC has already rolled to the next calendar date but US Eastern hasn't, a row written with {@code
     * current_date} lands "tomorrow" from the application's own point of view, so {@code findEffectiveOn}
     * (which requires {@code effectiveFrom <= asOf}) silently fails to see it as active -- reproduced only on
     * CI (UTC host) since local Docker Desktop's own current_date happened to stay aligned with local wall-
     * clock date. A fixed past date sidesteps the whole class of bug rather than picking a "less wrong" clock.
     */
    public static UUID insertCaseAssignment(JdbcTemplate jdbc, UUID householdId, UUID workerId) {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into case_assignment (id, household_id, worker_id, effective_from) "
                        + "values (?, ?, ?, ?)",
                id, householdId, workerId, BASE_EFFECTIVE_FROM);
        return id;
    }

    /**
     * An OUTSTANDING verification row -- {@link #threePersonWorkingHousehold} doesn't create one itself
     * (it bypasses {@code IntakeService} entirely), so tests that need one seed it directly, same reason
     * {@link #insertWorker} exists.
     */
    public static UUID insertVerification(JdbcTemplate jdbc, UUID programRequestId, String dataElement) {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into verification (id, program_request_id, data_element, status, due_on) "
                        + "values (?, ?, ?, 'OUTSTANDING', ?)",
                id, programRequestId, dataElement, BASE_EFFECTIVE_FROM.plusDays(10));
        return id;
    }

    private static UUID insertPerson(JdbcTemplate jdbc, String firstName, String lastName, LocalDate dob) {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
                        + "values (?, ?, ?, ?, ?, 'X')",
                id, firstName, lastName, dob, "tok-" + id);
        return id;
    }

    private static UUID insertHousehold(JdbcTemplate jdbc, UUID headPersonId) {
        UUID id = UUID.randomUUID();
        jdbc.update(
                "insert into household (id, head_person_id, county, address_line1, city, state, zip_code) "
                        + "values (?, ?, 'Test County', '123 Test St', 'Testville', 'TS', '00000')",
                id, headPersonId);
        return id;
    }

    private static void insertHouseholdMember(JdbcTemplate jdbc, UUID householdId, UUID personId, String relationship) {
        jdbc.update(
                "insert into household_member (id, household_id, person_id, relationship, effective_from) "
                        + "values (?, ?, ?, ?, ?)",
                UUID.randomUUID(), householdId, personId, relationship, BASE_EFFECTIVE_FROM);
    }

    private static void insertIncome(JdbcTemplate jdbc, UUID personId, String incomeType, boolean earned, String amount) {
        insertIncome(jdbc, personId, incomeType, earned, amount, BASE_EFFECTIVE_FROM);
    }

    private static void insertIncome(JdbcTemplate jdbc, UUID personId, String incomeType, boolean earned,
                                      String amount, LocalDate effectiveFrom) {
        jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, monthly_amount, effective_from) "
                        + "values (?, ?, ?, ?, ?, ?)",
                UUID.randomUUID(), personId, incomeType, earned, new BigDecimal(amount), effectiveFrom);
    }

    private static void insertExpense(JdbcTemplate jdbc, UUID personId, String expenseType, String amount) {
        jdbc.update(
                "insert into expense_record (id, person_id, expense_type, monthly_amount, effective_from) "
                        + "values (?, ?, ?, ?, ?)",
                UUID.randomUUID(), personId, expenseType, new BigDecimal(amount), BASE_EFFECTIVE_FROM);
    }

    private static void insertLivingArrangement(JdbcTemplate jdbc, UUID householdId, String arrangementType) {
        jdbc.update(
                "insert into living_arrangement (id, household_id, arrangement_type, effective_from) "
                        + "values (?, ?, ?, ?)",
                UUID.randomUUID(), householdId, arrangementType, BASE_EFFECTIVE_FROM);
    }

    private static UUID insertApplicationAndRequest(JdbcTemplate jdbc, UUID householdId) {
        UUID applicationId = UUID.randomUUID();
        jdbc.update(
                "insert into application (id, household_id, submitted_at, channel) values (?, ?, now(), 'ONLINE')",
                applicationId, householdId);
        UUID programRequestId = UUID.randomUUID();
        jdbc.update(
                "insert into program_request (id, application_id, program_code, status, requested_on) "
                        + "values (?, ?, 'SNAP', 'SUBMITTED', ?)",
                programRequestId, applicationId, BASE_EFFECTIVE_FROM);
        return programRequestId;
    }

    public record Ids(UUID householdId, UUID headPersonId, UUID programRequestId) {
    }
}
