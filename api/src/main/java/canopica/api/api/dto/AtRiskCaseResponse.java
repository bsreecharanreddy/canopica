package canopica.api.api.dto;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * One row of the Case SLA/Compliance Monitor's at-risk queue (Phase 4 Task 6). {@code daysRemaining} is
 * computed live against SNAP's 7-day-expedited/30-day standard from {@code requested_on} -- the same
 * standard {@code mart_processing_timeliness} applies to already-decided cases, applied here to still-pending
 * ones. {@code stallReason}/{@code stallReasonGeneratedAt} are {@code null} until {@code ai/sla_monitor}'s own
 * refresh job has run at least once for this case -- pre-generated, not computed on this request (design doc
 * §2.4: no LLM call on the live request path).
 */
public record AtRiskCaseResponse(
        UUID programRequestId, String householdHeadName, LocalDate requestedOn, boolean isExpedited,
        int daysRemaining, String stallReason, Instant stallReasonGeneratedAt) {
}
