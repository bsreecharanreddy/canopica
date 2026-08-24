package canopica.portal.policy;

/**
 * The copilot could not produce a draft -- either it is unreachable, or it ran and declined to return
 * something it could stand behind (the AI service answers 502 for the latter; see
 * {@code canopica_ai...rule_authoring.api}).
 *
 * <p>One exception for both because the admin's next action is the same either way: try again, or paste a
 * clearer excerpt. What must not happen is a half-populated proposal reaching the review screen, where a
 * reviewer has no way to see which figures are missing.
 */
public class RuleAuthoringUnavailableException extends RuntimeException {

    public RuleAuthoringUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
