package canopica.rules;

import java.math.BigDecimal;
import java.math.RoundingMode;
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

    private final DMNRuntime runtime;
    private final DMNModel model;

    public SnapDmnEvaluator() {
        this.runtime = DMNRuntimeBuilder.fromDefaults()
                .buildConfiguration()
                .fromClasspathResource("dmn/snap-eligibility.dmn", SnapDmnEvaluator.class)
                .getOrElseThrow(e -> new DmnEvaluationException("cannot load DMN model", e));
        this.model = runtime.getModel(NAMESPACE, MODEL_NAME);
        if (model == null) {
            throw new DmnEvaluationException(
                    "DMN model " + NAMESPACE + "#" + MODEL_NAME + " not found on the classpath");
        }
    }

    /** DMN compilation messages for the loaded model; empty on a clean load. */
    public List<String> modelMessages() {
        return model.getMessages().stream().map(Object::toString).toList();
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
