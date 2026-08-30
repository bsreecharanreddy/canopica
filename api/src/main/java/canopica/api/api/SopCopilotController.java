package canopica.api.api;

import canopica.api.sop.SopAnswer;
import canopica.api.sop.SopCopilotClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * Caseworker SOP Copilot (Phase 4 Task 7). {@code SecurityConfig} restricts {@code /api/sop-copilot/**} to
 * {@code hasAnyRole("WORKER", "SUPERVISOR")} -- unlike the review-queue endpoints elsewhere in this phase,
 * this is a caseworker-facing tool (design doc §2.5), not a supervisor-only triage surface. No persistence,
 * no audit event: a stateless ask/answer pass-through to {@link SopCopilotClient}, the same shape a direct
 * browser-to-Python call would have if this capability didn't need worker-realm-gated authorization first.
 */
@RestController
class SopCopilotController {

    private final SopCopilotClient sopCopilotClient;

    SopCopilotController(SopCopilotClient sopCopilotClient) {
        this.sopCopilotClient = sopCopilotClient;
    }

    record AskRequest(String question) {
    }

    @PostMapping("/api/sop-copilot/ask")
    SopAnswer ask(@RequestBody AskRequest request) {
        return sopCopilotClient.ask(request.question());
    }
}
