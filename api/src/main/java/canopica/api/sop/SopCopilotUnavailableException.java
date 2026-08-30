package canopica.api.sop;

/**
 * The SOP Copilot could not produce an answer -- unreachable, or a real processing failure on its own side.
 * One exception for both, same reasoning {@link canopica.api.policy.RuleAuthoringUnavailableException}'s own
 * doc comment gives: the caller's next action is the same either way (try again), and what must not happen
 * is a partial or fabricated answer reaching the caseworker with no signal that something went wrong.
 */
public class SopCopilotUnavailableException extends RuntimeException {

    public SopCopilotUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
