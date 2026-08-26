package canopica.api.policy;

/** Thrown when no published policy parameter set covers a requested date or household size. */
public class PolicyParameterNotFoundException extends RuntimeException {

    public PolicyParameterNotFoundException(String message) {
        super(message);
    }
}
