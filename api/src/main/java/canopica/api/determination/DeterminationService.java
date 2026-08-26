package canopica.api.determination;

import canopica.rules.SnapDecision;
import java.time.LocalDate;
import java.util.UUID;

public interface DeterminationService {

    /** Evaluates one program request as of a date and appends the result. */
    UUID determine(UUID programRequestId, LocalDate asOf, LocalDate benefitMonth, String decidedBy);

    /**
     * Re-evaluates a stored determination against its own recorded parameter
     * set version and returns the result WITHOUT persisting anything.
     */
    SnapDecision reproduce(UUID determinationId);
}
