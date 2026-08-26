package canopica.api.api.dto;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

class EffectiveRangeValidator implements ConstraintValidator<EffectiveRange, EffectiveDated> {

    @Override
    public boolean isValid(EffectiveDated value, ConstraintValidatorContext context) {
        if (value == null || value.effectiveFrom() == null || value.effectiveTo() == null) {
            // Missing effectiveFrom is a separate @NotNull concern; a null effectiveTo is a valid open-ended record.
            return true;
        }
        return !value.effectiveTo().isBefore(value.effectiveFrom());
    }
}
