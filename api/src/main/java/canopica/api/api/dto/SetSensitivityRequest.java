package canopica.api.api.dto;

/** {@code reason} is expected but not enforced non-null -- un-flagging (isSensitive=false) has none. */
public record SetSensitivityRequest(boolean isSensitive, String reason) {
}
