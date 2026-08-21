package ies.portal.intake;

/** A structurally valid (bean-validation-passing) intake that is still semantically wrong, e.g. no head of household. */
public class InvalidIntakeException extends RuntimeException {

    public InvalidIntakeException(String message) {
        super(message);
    }
}
