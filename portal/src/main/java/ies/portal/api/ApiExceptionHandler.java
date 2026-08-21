package ies.portal.api;

import ies.portal.intake.InvalidIntakeException;
import ies.portal.policy.PolicyParameterNotFoundException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException ex) {
        List<Map<String, String>> errors = new ArrayList<>();
        for (FieldError fieldError : ex.getBindingResult().getFieldErrors()) {
            errors.add(Map.of("field", fieldError.getField(), "message", messageOf(fieldError)));
        }
        for (ObjectError objectError : ex.getBindingResult().getGlobalErrors()) {
            errors.add(Map.of("field", objectError.getObjectName(), "message", messageOf(objectError)));
        }
        return ResponseEntity.badRequest().body(Map.of("errors", errors));
    }

    @ExceptionHandler(InvalidIntakeException.class)
    ResponseEntity<Map<String, Object>> handleInvalidIntake(InvalidIntakeException ex) {
        return ResponseEntity.badRequest().body(Map.of("errors", List.of(Map.of("message", ex.getMessage()))));
    }

    @ExceptionHandler(PolicyParameterNotFoundException.class)
    ResponseEntity<Map<String, Object>> handlePolicyParameterNotFound(PolicyParameterNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY).body(Map.of("message", ex.getMessage()));
    }

    @ExceptionHandler({NoSuchElementException.class, EmptyResultDataAccessException.class})
    ResponseEntity<Map<String, Object>> handleNotFound(RuntimeException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("message", ex.getMessage()));
    }

    private static String messageOf(ObjectError error) {
        return error.getDefaultMessage() == null ? "invalid value" : error.getDefaultMessage();
    }
}
