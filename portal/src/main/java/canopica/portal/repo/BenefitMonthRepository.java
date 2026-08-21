package canopica.portal.repo;

import canopica.portal.domain.BenefitMonth;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BenefitMonthRepository extends JpaRepository<BenefitMonth, UUID> {
}
