package canopica.api.api.dto;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Class-level constraint: an open-ended {@code effectiveTo} (null) is valid; a set one must not precede {@code effectiveFrom}. */
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = EffectiveRangeValidator.class)
public @interface EffectiveRange {

    String message() default "effectiveTo must not be before effectiveFrom";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
