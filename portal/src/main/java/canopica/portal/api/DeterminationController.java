package canopica.portal.api;

import canopica.portal.api.dto.DetermineRequest;
import canopica.portal.api.dto.DeterminationResponse;
import canopica.portal.determination.DeterminationService;
import canopica.portal.repo.EligibilityDeterminationRepository;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/program-requests/{programRequestId}/determinations")
class DeterminationController {

    private final DeterminationService determinationService;
    private final EligibilityDeterminationRepository determinations;

    DeterminationController(DeterminationService determinationService,
                             EligibilityDeterminationRepository determinations) {
        this.determinationService = determinationService;
        this.determinations = determinations;
    }

    @PostMapping
    ResponseEntity<DeterminationResponse> determine(@PathVariable UUID programRequestId,
            @Valid @RequestBody DetermineRequest request, Authentication authentication) {
        UUID determinationId = determinationService.determine(
                programRequestId, request.asOfDate(), request.benefitMonth(), authentication.getName());
        var determination = determinations.findById(determinationId).orElseThrow();
        return ResponseEntity.status(HttpStatus.CREATED).body(DeterminationResponse.from(determination));
    }
}
