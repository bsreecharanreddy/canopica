package canopica.portal.api.dto;

import java.time.LocalDate;

/** Implemented by any intake DTO carrying an effective date range, so {@link EffectiveRange} can validate it. */
public interface EffectiveDated {

    LocalDate effectiveFrom();

    LocalDate effectiveTo();
}
