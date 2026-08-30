package canopica.api.sop;

import java.util.List;

/** Mirrors {@code canopica_ai.sop_copilot.service.SopAnswer}'s own JSON shape. */
public record SopAnswer(String answer, List<String> citations, boolean abstained) {
}
