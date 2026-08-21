package ies.portal.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Pins "now"/"today" to {@code ies.timezone} (application.yml) rather than the host's default zone --
 * benefit months, effective dating, and the annual October 1 parameter change are all civil-calendar
 * concepts, not instant-in-UTC ones.
 */
@Configuration
class ClockConfig {

    @Bean
    Clock clock(@Value("${ies.timezone}") String zoneId) {
        return Clock.system(ZoneId.of(zoneId));
    }
}
