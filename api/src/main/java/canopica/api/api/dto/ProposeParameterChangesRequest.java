package canopica.api.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * The policy-document excerpt an admin pastes in. Diffed against whatever set is in force today -- the admin
 * does not pick a parameter set, because "the one currently in force" is the only answer that isn't a way to
 * make a mistake.
 */
public record ProposeParameterChangesRequest(
        // A prompt-budget bound, not a policy one, and a measured one (2026-08-23). The copilot's prompt is
        // the excerpt plus the *whole* current parameter list, which for the real FY2026 set is 39 figures
        // and roughly 4,200 characters on its own. At 6,000 characters of excerpt the prompt comes to about
        // 10,200 characters -- comfortably inside llama3.2:3b's 4,096-token window once `num_predict` is
        // reserved. 8,000 was tried first and measured at 12,186 characters / 3,105 tokens, which fits but
        // sits close enough to the ceiling that a slightly larger parameter set would push it over.
        // `OllamaClient` refuses anything that would not fit rather than letting it be truncated, so the
        // failure mode of getting this wrong is a clear error, not a silently partial prompt.
        @NotBlank @Size(max = 6000) String documentExcerpt) {}
