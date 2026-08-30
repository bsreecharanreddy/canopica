package canopica.api.sop;

/**
 * This API's view of the Caseworker SOP Copilot (Phase 4 design doc §2.5) -- an interface rather than a
 * concrete HTTP client for the same reason {@link canopica.api.policy.RuleAuthoringClient} is one: a test
 * needing to drive a controller that calls this shouldn't need a multi-gigabyte model in the loop. The
 * model's own behaviour has its own coverage, against a real model, in {@code ai/tests/test_sop_copilot.py}.
 */
public interface SopCopilotClient {

    /**
     * @throws SopCopilotUnavailableException if the copilot cannot be reached, or fails on its own side.
     *     Abstention is not an error -- a well-formed {@link SopAnswer} with {@code abstained=true} is the
     *     copilot correctly declining to guess, and is returned normally.
     */
    SopAnswer ask(String question);
}
