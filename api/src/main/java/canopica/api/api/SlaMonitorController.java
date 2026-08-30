package canopica.api.api;

import canopica.api.api.dto.AtRiskCaseResponse;
import canopica.api.caseload.AtRiskCaseQuery;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The Case SLA/Compliance Monitor's read surface (Phase 4 Task 6). {@code SecurityConfig} restricts {@code
 * /api/sla/**} to the SUPERVISOR role, same cross-caseload triage-queue reasoning {@code /api/fraud/**} and
 * {@code /api/qc/**} already document. A plain delegate to {@link AtRiskCaseQuery} -- no LLM call, no
 * write, on this or any other request path this controller serves (design doc §2.4).
 */
@RestController
class SlaMonitorController {

    private final AtRiskCaseQuery atRiskCaseQuery;

    SlaMonitorController(AtRiskCaseQuery atRiskCaseQuery) {
        this.atRiskCaseQuery = atRiskCaseQuery;
    }

    @GetMapping("/api/sla/at-risk-queue")
    List<AtRiskCaseResponse> atRiskQueue() {
        return atRiskCaseQuery.findAtRiskCases();
    }
}
