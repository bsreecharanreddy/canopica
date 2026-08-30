package canopica.api.api.dto;

/**
 * The {@code run-sample} endpoint's own summary (Phase 4 Task 4) -- counts only, not one row per sampled
 * case: the caller is Airflow's own scheduled task, not a human reviewer, and Task 5's review-queue endpoint
 * is the real per-case read path.
 */
public record QcSampleRunResponse(int sampled, int flagged) {
}
