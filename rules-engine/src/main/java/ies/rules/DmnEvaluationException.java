package ies.rules;

/** Thrown when the DMN model fails to load or an evaluation produces an error. */
public class DmnEvaluationException extends RuntimeException {

    public DmnEvaluationException(String message) {
        super(message);
    }

    public DmnEvaluationException(String message, Throwable cause) {
        super(message, cause);
    }
}
