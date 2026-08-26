package canopica.api.config;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;
import java.math.BigDecimal;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Money leaves this service as a JSON string, never a JSON number.
 *
 * <p>This repo states "money never round-trips through a float" in the domain model, the DTOs, and
 * {@code ui/src/api/types.ts}, and it was true everywhere except the last hop: Jackson serialises
 * {@link BigDecimal} as a bare JSON number by default, so {@code JSON.parse} in the browser turned a $649.00
 * award into the double {@code 649} before any component saw it. The visible symptom is cents disappearing
 * from the screen; the invisible one is that every downstream consumer was reading a float and the
 * TypeScript types said otherwise.
 *
 * <p>Registered globally rather than as {@code @JsonFormat(shape = STRING)} on each field, because a
 * convention enforced by remembering an annotation is a convention that lasts until the next DTO. Every
 * {@code BigDecimal} in this system is a dollar amount or a rate, and both want to be strings.
 * {@code toPlainString()} rather than {@code toString()} so a value never renders in scientific notation,
 * and so the scale the database stored ("649.00", not "649") survives intact.
 *
 * <p>Deserialisation is deliberately untouched: Jackson already reads a JSON string into a
 * {@code BigDecimal} without losing precision, which is why the intake DTOs have accepted string amounts
 * from the browser since Phase 1a.
 */
@Configuration
class JacksonConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer moneyAsJsonString() {
        return builder -> builder.serializerByType(BigDecimal.class, new JsonSerializer<BigDecimal>() {
            @Override
            public void serialize(BigDecimal value, JsonGenerator generator, SerializerProvider provider)
                    throws IOException {
                generator.writeString(value.toPlainString());
            }
        });
    }
}
