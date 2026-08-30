package canopica.api.qc;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import canopica.api.determination.DeterminationService;
import canopica.api.pgmq.PgmqService;
import canopica.rules.SnapDecision;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.annotation.Lazy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Samples recently decided, eligible determinations and re-derives each via the existing {@link
 * DeterminationService#reproduce}, diffing the fresh result against what was actually recorded (Phase 4
 * design doc §2.3). No new DMN-evaluation code -- {@code reproduce()} already exists (Phase 1a); this is a
 * new caller of it.
 *
 * <p>Sampling, not exhaustive re-derivation: modeled on the real federal SNAP QC process's own
 * statistically-valid-sample cadence, not an arbitrary cost cut (design doc §2.3). {@link #DEFAULT_SAMPLE_RATE}
 * is a stated starting default -- unmeasured against this project's real determination volume, same posture
 * {@code fraud_scoring_consumer.py}'s own {@code _REVIEW_THRESHOLD} comment takes for its unmeasured figure --
 * chosen higher than the real program's roughly 1-in-1000 rate because this project's own data volume would
 * sample zero cases at that rate; revisit once there's real volume to size against.
 */
@Service
public class QcSamplingService {

    /** 10% of the eligible, unsampled population in the lookback window -- see the class doc comment. */
    static final double DEFAULT_SAMPLE_RATE = 0.10;

    /** How far back "recently decided" reaches -- matches the Airflow task's own trigger cadence (Task 4
     * plan Step 5): frequent enough sampling that a 30-day window always has a fresh population to draw from. */
    static final int LOOKBACK_DAYS = 30;

    private final JdbcTemplate jdbc;
    private final DeterminationService determinations;
    private final PaymentErrorReviewRepository reviews;
    private final PgmqService pgmq;
    private final ObjectMapper objectMapper;
    private final QcSamplingService self;

    // `self` is a Spring-AOP-proxied reference to this very bean, injected lazily (breaking the
    // constructor cycle a bean depending on itself would otherwise create). Without it, runSample()'s
    // own `this.sampleOne(...)` calls below would be plain Java self-invocation, which bypasses the
    // @Transactional proxy entirely (a well-known Spring AOP limitation) -- silently downgrading the
    // "row insert and its conditional enqueue share one transaction" guarantee this whole architecture
    // depends on (constraint 17) into two separately auto-committed statements. Routing the call
    // through `self` instead keeps every sampleOne() call going through the real proxy.
    QcSamplingService(JdbcTemplate jdbc, DeterminationService determinations, PaymentErrorReviewRepository reviews,
                       PgmqService pgmq, ObjectMapper objectMapper, @Lazy QcSamplingService self) {
        this.jdbc = jdbc;
        this.determinations = determinations;
        this.reviews = reviews;
        this.pgmq = pgmq;
        this.objectMapper = objectMapper;
        this.self = self;
    }

    /** {@link #DEFAULT_SAMPLE_RATE} applied against the current eligible, unsampled population -- what the
     * Airflow-triggered endpoint uses when the caller doesn't name an explicit size. */
    public int computeDefaultSampleSize() {
        Integer eligiblePopulation = jdbc.queryForObject(sampleSelectionSql("count(*)"), Integer.class);
        int population = eligiblePopulation == null ? 0 : eligiblePopulation;
        return (int) Math.ceil(population * DEFAULT_SAMPLE_RATE);
    }

    /**
     * Samples up to {@code sampleSize} eligible determinations decided in the last {@link #LOOKBACK_DAYS}
     * days that have never been sampled before, re-derives each, and writes a {@code payment_error_review}
     * row for every one of them -- not only the ones with a nonzero diff, since an unflagged sample is
     * itself evidence {@code mart_payment_accuracy} needs (Task 4 plan's own Interfaces note). Each row is
     * its own transaction ({@link #sampleOne}) so one bad case (a missing trace, a corrupted snapshot) can't
     * roll back every other row this same run already wrote.
     */
    public List<PaymentErrorReview> runSample(int sampleSize) {
        if (sampleSize <= 0) {
            return List.of();
        }
        List<UUID> determinationIds = jdbc.queryForList(
                sampleSelectionSql("id") + " order by random() limit ?", UUID.class, sampleSize);

        List<PaymentErrorReview> results = new ArrayList<>();
        for (UUID determinationId : determinationIds) {
            results.add(self.sampleOne(determinationId));
        }
        return results;
    }

    @Transactional
    PaymentErrorReview sampleOne(UUID determinationId) {
        BigDecimal originalAmount = jdbc.queryForObject(
                "select benefit_amount from eligibility_determination where id = ?", BigDecimal.class, determinationId);

        SnapDecision reproduced = determinations.reproduce(determinationId);
        BigDecimal reproducedAmount = reproduced.benefitAmount();
        BigDecimal errorAmount = reproducedAmount.subtract(originalAmount);

        PaymentErrorReview review = new PaymentErrorReview(
                UUID.randomUUID(), determinationId, originalAmount, reproducedAmount, errorAmount,
                writeJson(reproduced.trace()));
        PaymentErrorReview saved = reviews.save(review);

        // Constraint 17 again (see JdbcDeterminationService's own comment on the identical pattern):
        // shares this method's own transaction, so the enqueue can never fire for a row that ends up
        // rolled back and never silently fails to fire for one that commits.
        if (errorAmount.compareTo(BigDecimal.ZERO) != 0) {
            pgmq.send("qc_summary", Map.of("payment_error_review_id", saved.getId().toString()));
        }
        return saved;
    }

    /** Shared by {@link #computeDefaultSampleSize} and {@link #runSample} so the population counted and the
     * population sampled from can never silently drift apart. A denial produces no payment, so there's
     * nothing to review for accuracy (same restriction {@code mart_payment_accuracy.sql}'s own comment
     * already states); a determination already sampled (any prior cycle) is excluded so re-running this
     * job doesn't re-review the same case forever. */
    private String sampleSelectionSql(String projection) {
        return "select " + projection + " from eligibility_determination "
                + "where eligible = true and decided_at >= now() - interval '" + LOOKBACK_DAYS + " days' "
                + "and id not in (select determination_id from payment_error_review)";
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("failed to serialize reproduced determination trace data", e);
        }
    }
}
