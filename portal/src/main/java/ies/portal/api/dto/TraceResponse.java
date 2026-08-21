package ies.portal.api.dto;

import com.fasterxml.jackson.databind.JsonNode;

public record TraceResponse(
        JsonNode inputSnapshot, JsonNode decisionResults, String dmnModelHash, String policyParameterVersion) {
}
