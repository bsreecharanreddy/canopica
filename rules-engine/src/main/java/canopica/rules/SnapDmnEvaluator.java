package canopica.rules;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.kie.dmn.api.core.DMNContext;
import org.kie.dmn.api.core.DMNModel;
import org.kie.dmn.api.core.DMNResult;
import org.kie.dmn.api.core.DMNRuntime;
import org.kie.dmn.core.internal.utils.DMNRuntimeBuilder;

/**
 * Evaluates the SNAP eligibility DMN model. No Spring, no database, no clock
 * of its own -- {@link SnapFacts} and {@link SnapPolicyParameters} are both
 * already resolved by the caller before this runs, which is what makes an
 * evaluation reproducible: replaying the exact same two inputs against this
 * same model always produces the exact same {@link SnapDecision}.
 */
public final class SnapDmnEvaluator {

    private static final String NAMESPACE = "https://canopica/dmn/snap";
    private static final String MODEL_NAME = "snap-eligibility";
    private static final String CLASSPATH_RESOURCE = "dmn/snap-eligibility.dmn";

    /**
     * Hardcoded rather than read from JAR manifest metadata: package
     * {@code Implementation-Version} is only populated when running from a
     * packaged jar with the right manifest entries, not when running tests
     * against {@code target/classes} -- which is every test in this repo.
     * Keep in sync with the parent POM's {@code kie.version} property.
     */
    public static final String ENGINE_VERSION = "kie-dmn-core-10.2.0";

    private final DMNRuntime runtime;
    private final DMNModel model;
    private final String modelHash;

    public SnapDmnEvaluator() {
        this.runtime = DMNRuntimeBuilder.fromDefaults()
                .buildConfiguration()
                .fromClasspathResource(CLASSPATH_RESOURCE, SnapDmnEvaluator.class)
                .getOrElseThrow(e -> new DmnEvaluationException("cannot load DMN model", e));
        this.model = runtime.getModel(NAMESPACE, MODEL_NAME);
        if (model == null) {
            throw new DmnEvaluationException(
                    "DMN model " + NAMESPACE + "#" + MODEL_NAME + " not found on the classpath");
        }
        this.modelHash = sha256OfClasspathResource(CLASSPATH_RESOURCE);
    }

    /** DMN compilation messages for the loaded model; empty on a clean load. */
    public List<String> modelMessages() {
        return model.getMessages().stream().map(Object::toString).toList();
    }

    /**
     * SHA-256 of the exact {@code .dmn} file this evaluator loaded, so a
     * later re-derivation can prove it ran against the same model, not just
     * the same numbers.
     */
    public String modelHash() {
        return modelHash;
    }

    private static String sha256OfClasspathResource(String resourcePath) {
        try (InputStream in = SnapDmnEvaluator.class.getClassLoader().getResourceAsStream(resourcePath)) {
            if (in == null) {
                throw new DmnEvaluationException("classpath resource not found: " + resourcePath);
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(in.readAllBytes()));
        } catch (IOException e) {
            throw new DmnEvaluationException("failed to read " + resourcePath + " for hashing", e);
        } catch (NoSuchAlgorithmException e) {
            throw new DmnEvaluationException("SHA-256 not available", e);
        }
    }

    public SnapDecision evaluate(SnapFacts facts, SnapPolicyParameters parameters) {
        DMNContext context = runtime.newContext();
        context.set("Facts", asMap(facts));
        context.set("Parameters", asMap(parameters));

        DMNResult result = runtime.evaluateAll(model, context);
        if (result.hasErrors()) {
            throw new DmnEvaluationException("DMN evaluation failed: " + result.getMessages());
        }

        Map<String, Object> trace = new LinkedHashMap<>();
        result.getDecisionResults().forEach(dr -> trace.put(dr.getDecisionName(), dr.getResult()));

        @SuppressWarnings("unchecked")
        Map<String, Object> determination =
                (Map<String, Object>) result.getDecisionResultByName("Determination").getResult();

        return new SnapDecision(
                (Boolean) determination.get("eligible"),
                toMoney(determination.get("benefitAmount")),
                (String) determination.get("reasonCode"),
                Map.copyOf(trace));
    }

    private static Map<String, Object> asMap(SnapFacts facts) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("householdSize", facts.householdSize());
        map.put("earnedIncome", facts.earnedIncome());
        map.put("unearnedIncome", facts.unearnedIncome());
        map.put("dependentCareCost", facts.dependentCareCost());
        map.put("medicalExpense", facts.medicalExpense());
        map.put("shelterCost", facts.shelterCost());
        map.put("utilityCost", facts.utilityCost());
        map.put("hasElderlyOrDisabledMember", facts.hasElderlyOrDisabledMember());
        map.put("categoricallyEligible", facts.categoricallyEligible());
        return map;
    }

    private static Map<String, Object> asMap(SnapPolicyParameters parameters) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("grossIncomeLimit", parameters.grossIncomeLimit());
        map.put("netIncomeLimit", parameters.netIncomeLimit());
        map.put("standardDeduction", parameters.standardDeduction());
        map.put("earnedIncomeDeductionRate", parameters.earnedIncomeDeductionRate());
        map.put("medicalExpenseThreshold", parameters.medicalExpenseThreshold());
        map.put("excessShelterCap", parameters.excessShelterCap());
        map.put("shelterIncomeShare", parameters.shelterIncomeShare());
        map.put("maxAllotment", parameters.maxAllotment());
        map.put("minimumBenefit", parameters.minimumBenefit());
        map.put("minimumBenefitMaxHouseholdSize", parameters.minimumBenefitMaxHouseholdSize());
        map.put("benefitReductionRate", parameters.benefitReductionRate());
        return map;
    }

    private static BigDecimal toMoney(Object value) {
        return ((BigDecimal) value).setScale(2, RoundingMode.HALF_UP);
    }
}
