package canopica.rules;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * Verifies the kie-dmn bootstrap works and every named decision fires --
 * the one thing in this module that can't be verified just by reading the
 * DMN XML. Written first so a model-authoring mistake fails here instead
 * of confusingly inside a scenario test.
 */
class DmnModelSanityTest {

    @Test
    void theModelLoadsWithNoCompilationMessages() {
        SnapDmnEvaluator evaluator = new SnapDmnEvaluator();
        assertThat(evaluator.modelMessages())
                .as("DMN compilation messages")
                .isEmpty();
    }

    @Test
    void everyNamedDecisionAppearsInTheTraceOfATrivialEvaluation() {
        SnapDecision decision = new SnapDmnEvaluator().evaluate(
                TestFixtures.facts().householdSize(1).build(),
                TestFixtures.fy2025Parameters(1));

        assertThat(decision.trace()).containsKeys(
                "Gross Income", "Gross Income Test", "Earned Income Deduction",
                "Medical Expense Deduction", "Adjusted Income", "Shelter Excess",
                "Excess Shelter Deduction", "Net Income", "Net Income Test",
                "Computed Benefit", "Benefit Amount", "Determination");
    }
}
