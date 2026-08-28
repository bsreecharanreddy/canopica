package canopica.api.repo;

import canopica.api.notice.Notice;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NoticeRepository extends JpaRepository<Notice, UUID> {

    /** Backs Task 6's review queue -- {@code notice_review_queue_idx} (V20) covers exactly this shape. */
    List<Notice> findByProgramRequestIdInAndStatusOrderByCreatedAtAsc(
            List<UUID> programRequestIds, String status);
}
