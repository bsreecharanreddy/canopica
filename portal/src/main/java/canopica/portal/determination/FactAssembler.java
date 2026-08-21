package canopica.portal.determination;

import canopica.rules.SnapFacts;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * Reads effective-dated household/person records as of one date and shapes
 * them into a {@link SnapFacts}. Uses direct JDBC rather than the JPA
 * repositories' as-of queries, since this needs to join across several
 * effective-dated tables in a single pass rather than fetch each one
 * separately and merge in Java.
 */
@Component
class FactAssembler {

    private final JdbcTemplate jdbc;

    FactAssembler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    SnapFacts assemble(UUID householdId, LocalDate asOf) {
        List<UUID> memberPersonIds = jdbc.query(
                """
                select person_id from household_member
                where household_id = ? and effective_from <= ?
                  and (effective_to is null or effective_to >= ?)
                """,
                (rs, rowNum) -> (UUID) rs.getObject("person_id"),
                householdId, asOf, asOf);

        int householdSize = memberPersonIds.size();

        String earnedIncome = sumIncome(memberPersonIds, asOf, true);
        String unearnedIncome = sumIncome(memberPersonIds, asOf, false);

        String dependentCareCost = sumExpense(memberPersonIds, asOf, "DEPENDENT_CARE");
        String medicalExpense = sumExpense(memberPersonIds, asOf, "MEDICAL");
        String shelterCost = sumExpenseAny(memberPersonIds, asOf,
                List.of("RENT_OR_MORTGAGE", "PROPERTY_TAX", "HOME_INSURANCE"));
        String utilityCost = sumExpense(memberPersonIds, asOf, "UTILITIES");

        boolean hasElderlyOrDisabledMember = hasElderlyMember(memberPersonIds, asOf)
                || hasEffectiveDisabilityRecord(memberPersonIds, asOf);
        boolean categoricallyEligible = hasSsiIncome(memberPersonIds, asOf);

        return new SnapFacts(
                householdSize,
                new java.math.BigDecimal(earnedIncome),
                new java.math.BigDecimal(unearnedIncome),
                new java.math.BigDecimal(dependentCareCost),
                new java.math.BigDecimal(medicalExpense),
                new java.math.BigDecimal(shelterCost),
                new java.math.BigDecimal(utilityCost),
                hasElderlyOrDisabledMember,
                categoricallyEligible);
    }

    private String sumIncome(List<UUID> personIds, LocalDate asOf, boolean earned) {
        if (personIds.isEmpty()) {
            return "0";
        }
        String placeholders = placeholders(personIds.size());
        Object[] args = withDates(personIds, asOf, earned);
        String sql = """
                select coalesce(sum(monthly_amount), 0) from income_record
                where person_id in (%s) and effective_from <= ? and (effective_to is null or effective_to >= ?)
                  and is_earned = ?
                """.formatted(placeholders);
        return jdbc.queryForObject(sql, String.class, args);
    }

    private String sumExpense(List<UUID> personIds, LocalDate asOf, String expenseType) {
        return sumExpenseAny(personIds, asOf, List.of(expenseType));
    }

    private String sumExpenseAny(List<UUID> personIds, LocalDate asOf, List<String> expenseTypes) {
        if (personIds.isEmpty()) {
            return "0";
        }
        String personPlaceholders = placeholders(personIds.size());
        String typePlaceholders = placeholders(expenseTypes.size());
        Object[] args = concat(personIds.toArray(), new Object[] {asOf, asOf}, expenseTypes.toArray());
        String sql = """
                select coalesce(sum(monthly_amount), 0) from expense_record
                where person_id in (%s) and effective_from <= ? and (effective_to is null or effective_to >= ?)
                  and expense_type in (%s)
                """.formatted(personPlaceholders, typePlaceholders);
        return jdbc.queryForObject(sql, String.class, args);
    }

    private boolean hasElderlyMember(List<UUID> personIds, LocalDate asOf) {
        if (personIds.isEmpty()) {
            return false;
        }
        LocalDate sixtyYearsAgo = asOf.minusYears(60);
        String placeholders = placeholders(personIds.size());
        Object[] args = concat(personIds.toArray(), new Object[] {sixtyYearsAgo});
        String sql = "select count(*) from person where id in (%s) and date_of_birth <= ?"
                .formatted(placeholders);
        Integer count = jdbc.queryForObject(sql, Integer.class, args);
        return count != null && count > 0;
    }

    private boolean hasEffectiveDisabilityRecord(List<UUID> personIds, LocalDate asOf) {
        if (personIds.isEmpty()) {
            return false;
        }
        String placeholders = placeholders(personIds.size());
        Object[] args = concat(personIds.toArray(), new Object[] {asOf, asOf});
        String sql = """
                select count(*) from disability_record
                where person_id in (%s) and effective_from <= ? and (effective_to is null or effective_to >= ?)
                """.formatted(placeholders);
        Integer count = jdbc.queryForObject(sql, Integer.class, args);
        return count != null && count > 0;
    }

    private boolean hasSsiIncome(List<UUID> personIds, LocalDate asOf) {
        if (personIds.isEmpty()) {
            return false;
        }
        String placeholders = placeholders(personIds.size());
        Object[] args = concat(personIds.toArray(), new Object[] {asOf, asOf});
        String sql = """
                select count(*) from income_record
                where person_id in (%s) and income_type = 'SSI'
                  and effective_from <= ? and (effective_to is null or effective_to >= ?)
                """.formatted(placeholders);
        Integer count = jdbc.queryForObject(sql, Integer.class, args);
        return count != null && count > 0;
    }

    private static String placeholders(int count) {
        return String.join(",", java.util.Collections.nCopies(count, "?"));
    }

    private static Object[] withDates(List<UUID> personIds, LocalDate asOf, boolean earned) {
        return concat(personIds.toArray(), new Object[] {asOf, asOf, earned});
    }

    private static Object[] concat(Object[]... arrays) {
        return java.util.Arrays.stream(arrays)
                .flatMap(java.util.Arrays::stream)
                .collect(Collectors.toList())
                .toArray();
    }
}
