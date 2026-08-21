package canopica.portal.api;

import canopica.portal.api.dto.IntakeRequest;
import canopica.portal.api.dto.IntakeResponse;
import canopica.portal.intake.IntakeResult;
import canopica.portal.intake.IntakeService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/applications")
class IntakeController {

    private final IntakeService intakeService;

    IntakeController(IntakeService intakeService) {
        this.intakeService = intakeService;
    }

    @PostMapping
    ResponseEntity<IntakeResponse> submit(@Valid @RequestBody IntakeRequest request, Authentication authentication) {
        IntakeResult result = intakeService.submit(request, authentication.getName());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new IntakeResponse(result.applicationId(), result.programRequestId()));
    }
}
