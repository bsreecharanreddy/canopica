package canopica.api.qc;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import canopica.api.determination.DeterminationService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Exercises {@link QcSamplingService} against a real Postgres -- a real re-derivation via the existing
 * {@link DeterminationService#reproduce}, a real {@code payment_error_review} row, and a real transactional
 * {@code qc_summary} enqueue only when the diff is nonzero (constraint 19/design doc §2.3).
 *
 * <p>{@link #sampleOne} tests exercise a specific, known determination directly rather than through {@link
 * QcSamplingService#runSample} -- {@code AbstractPostgresTest}'s shared, non-rolled-back Testcontainers
 * Postgres (same instance across every test method in this class) means {@code runSample}'s own {@code order
 * by random() limit N} selection can't be pinned to "exactly the row this test just created" without also
 * depending on what every other test method has or hasn't sampled yet. The two {@code runSample}-level tests
 * below are written to hold regardless of that shared state, the same way {@code FraudReviewControllerTest}'s
 * own tests scope their assertions to rows they themselves created.
 */
class QcSamplingServiceTest extends AbstractPostgresTest {

    /** V4 migration's real FY2026 parameter set -- genuinely different figures from FY2025's (e.g.
     * MAX_ALLOTMENT household size 3: 768 vs 785), not a synthetic fixture. */
    private static final UUID SNAP_FY2026_PARAMETER_SET_ID =
            UUID.fromString("9f1c0e10-0000-4000-8000-000000000002");

    @Autowired QcSamplingService qcSamplingService;
    @Autowired DeterminationService determinations;
    @Autowired JdbcTemplate jdbc;

    @Test
    void aDeterminationReproducedAgainstAMismatchedParameterSetSurfacesARealDiff() {
        UUID determinationId = insertDeterminationWithMismatchedParameterSet();

        PaymentErrorReview review = qcSamplingService.sampleOne(determinationId);

        assertThat(review.getDeterminationId()).isEqualTo(determinationId);
        assertThat(review.getOriginalAmount()).isEqualByComparingTo("649");
        assertThat(review.getReproducedAmount()).isNotEqualByComparingTo(review.getOriginalAmount());
        assertThat(review.getErrorAmount())
                .isEqualByComparingTo(review.getReproducedAmount().subtract(review.getOriginalAmount()));
        assertThat(review.getReproducedTrace()).contains("Benefit Amount");

        assertThat(jdbc.queryForObject(
                        "select count(*) from payment_error_review where determination_id = ?",
                        Integer.class, determinationId))
                .isEqualTo(1);
    }

    @Test
    void aNonzeroDiffEnqueuesQcSummaryInTheSameTransactionAsTheRowsInsert() {
        UUID determinationId = insertDeterminationWithMismatchedParameterSet();

        PaymentErrorReview review = qcSamplingService.sampleOne(determinationId);

        assertThat(jdbc.queryForObject(
                        "select count(*) from pgmq.q_qc_summary where message->>'payment_error_review_id' = ?",
                        Integer.class, review.getId().toString()))
                .isEqualTo(1);
    }

    @Test
    void aCleanReproductionIsStillRecordedButDoesNotEnqueueASummary() {
        UUID determinationId = determineThreePersonHousehold();

        PaymentErrorReview review = qcSamplingService.sampleOne(determinationId);

        assertThat(review.getErrorAmount()).isEqualByComparingTo(BigDecimal.ZERO);
        assertThat(jdbc.queryForObject(
                        "select count(*) from pgmq.q_qc_summary where message->>'payment_error_review_id' = ?",
                        Integer.class, review.getId().toString()))
                .isEqualTo(0);
    }

    @Test
    void runSampleNeverSelectsADeterminationAlreadySampled() {
        UUID determinationId = determineThreePersonHousehold();
        qcSamplingService.sampleOne(determinationId);

        // Whatever else this samples from other tests' leftover state doesn't matter -- the one
        // thing this asserts is that the row this test itself already sampled is never touched
        // again, which the table's own unique(determination_id) constraint would refuse outright.
        qcSamplingService.runSample(50);

        assertThat(jdbc.queryForObject(
                        "select count(*) from payment_error_review where determination_id = ?",
                        Integer.class, determinationId))
                .isEqualTo(1);
    }

    @Test
    void computeDefaultSampleSizeAppliesTheDefaultRateAgainstTheUnsampledPopulation() {
        for (int i = 0; i < 5; i++) {
            determineThreePersonHousehold();
        }
        int population = jdbc.queryForObject(
                "select count(*) from eligibility_determination where eligible = true "
                        + "and decided_at >= now() - interval '30 days' "
                        + "and id not in (select determination_id from payment_error_review)",
                Integer.class);

        assertThat(qcSamplingService.computeDefaultSampleSize())
                .isEqualTo((int) Math.ceil(population * QcSamplingService.DEFAULT_SAMPLE_RATE));
    }

    private UUID determineThreePersonHousehold() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        return determinations.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
    }

    /** Simulates the real failure mode QC exists to catch: an {@code eligibility_determination} row whose
     * recorded amount doesn't match what its own stored facts/parameter-set id would actually produce.
     * {@code eligibility_determination} is append-only (V5's trigger refuses any update), so this reuses a
     * genuine FY2025 determination's own real input snapshot, then inserts a second row directly -- bypassing
     * {@link DeterminationService#determine}, the same "below the API layer" posture {@link
     * CaseFixtures#insertFraudRiskScore} already takes -- pointing at FY2026's real, different parameters. */
    private UUID insertDeterminationWithMismatchedParameterSet() {
        UUID genuineId = determineThreePersonHousehold();
        String inputSnapshot = jdbc.queryForObject(
                "select input_snapshot::text from determination_trace where determination_id = ?",
                String.class, genuineId);

        UUID determinationId = UUID.randomUUID();
        UUID programRequestId = jdbc.queryForObject(
                "select program_request_id from eligibility_determination where id = ?", UUID.class, genuineId);
        jdbc.update(
                "insert into eligibility_determination (id, program_request_id, benefit_month, as_of_date, "
                        + "eligible, benefit_amount, reason_code, policy_parameter_set_id, policy_parameter_version, "
                        + "decided_by) values (?, ?, '2025-06-01', '2025-06-15', true, 649, 'ELIGIBLE', ?, "
                        + "'SNAP-FY2026', 'SYSTEM')",
                determinationId, programRequestId, SNAP_FY2026_PARAMETER_SET_ID);
        jdbc.update(
                "insert into determination_trace (id, determination_id, input_snapshot, decision_results, "
                        + "dmn_model_name, dmn_model_hash, engine_version) "
                        + "values (?, ?, ?::jsonb, '{}'::jsonb, 'snap-eligibility', 'test-hash', 'test')",
                UUID.randomUUID(), determinationId, inputSnapshot);
        return determinationId;
    }
}
