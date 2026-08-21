package ies.portal.policy;

import ies.portal.domain.PolicyParameter;
import ies.portal.repo.PolicyParameterRepository;
import ies.portal.repo.PolicyParameterSetRepository;
import ies.rules.SnapPolicyParameters;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

@Component
class JdbcPolicyParameterResolver implements PolicyParameterResolver {

    // Every size-scoped figure the resolver must find before it can build a
    // SnapPolicyParameters. Missing any one of these for a requested
    // household size is what distinguishes "size not covered" from "date
    // not covered" in the thrown exception's message.
    private static final List<String> SIZE_SCOPED =
            List.of("MAX_ALLOTMENT", "STANDARD_DEDUCTION", "GROSS_INCOME_LIMIT", "NET_INCOME_LIMIT");

    private final PolicyParameterSetRepository sets;
    private final PolicyParameterRepository parameters;

    JdbcPolicyParameterResolver(PolicyParameterSetRepository sets, PolicyParameterRepository parameters) {
        this.sets = sets;
        this.parameters = parameters;
    }

    @Override
    public SnapPolicyParameters resolveSnap(LocalDate asOf, int householdSize) {
        var set = sets.findEffectiveOn("SNAP", asOf).orElseThrow(() ->
                new PolicyParameterNotFoundException(
                        "no published SNAP parameter set covers " + asOf));

        // One query, then an in-memory index: a determination resolves ~14
        // parameters and should not issue 14 round trips.
        Map<String, BigDecimal> byName = parameters
                .findForSet(set.getId(), householdSize)
                .stream()
                .collect(Collectors.toMap(PolicyParameter::getName, PolicyParameter::getNumericValue));

        for (String required : SIZE_SCOPED) {
            if (!byName.containsKey(required)) {
                throw new PolicyParameterNotFoundException(
                        set.getVersionLabel() + " does not cover household size " + householdSize
                                + " (missing " + required + ")");
            }
        }

        return new SnapPolicyParameters(
                set.getVersionLabel(),
                set.getId(),
                byName.get("GROSS_INCOME_LIMIT"),
                byName.get("NET_INCOME_LIMIT"),
                byName.get("STANDARD_DEDUCTION"),
                byName.get("EARNED_INCOME_DEDUCTION_RATE"),
                byName.get("MEDICAL_EXPENSE_THRESHOLD"),
                byName.get("EXCESS_SHELTER_CAP"),
                byName.get("SHELTER_INCOME_SHARE"),
                byName.get("MAX_ALLOTMENT"),
                byName.get("MINIMUM_BENEFIT"),
                byName.get("MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE").intValueExact(),
                byName.get("BENEFIT_REDUCTION_RATE"));
    }
}
