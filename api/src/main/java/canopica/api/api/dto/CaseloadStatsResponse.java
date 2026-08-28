package canopica.api.api.dto;

import java.util.List;

public record CaseloadStatsResponse(int activeCases, int pendingDetermination, List<AuditEventResponse> recentEvents) {
}
