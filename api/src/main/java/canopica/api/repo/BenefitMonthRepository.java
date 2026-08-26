package canopica.api.repo;

import canopica.api.domain.BenefitMonth;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BenefitMonthRepository extends JpaRepository<BenefitMonth, UUID> {
}
