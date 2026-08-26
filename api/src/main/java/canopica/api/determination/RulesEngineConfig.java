package canopica.api.determination;

import canopica.rules.SnapDmnEvaluator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * The rules-engine module is deliberately Spring-free (see its README), so
 * this wires {@link SnapDmnEvaluator} into the application context as a
 * singleton -- its constructor parses the DMN model once, which is the
 * expensive part and shouldn't happen per-request.
 */
@Configuration
class RulesEngineConfig {

    @Bean
    SnapDmnEvaluator snapDmnEvaluator() {
        return new SnapDmnEvaluator();
    }
}
