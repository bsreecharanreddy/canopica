package canopica.api.notice;

import canopica.api.repo.NoticeRepository;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.springframework.stereotype.Service;

/**
 * Reads a {@link Notice} back for the case-facing review UI (Task 6 adds approve/reject/dispatch here).
 * Nothing writes a notice through this service in Task 5 -- the worker's {@code correspondence_consumer.py}
 * inserts the row directly, the same split {@link canopica.api.document.DocumentService}'s own {@code
 * upload}/worker-write split establishes for {@code document.extraction}.
 */
@Service
public class NoticeService {

    private final NoticeRepository notices;

    NoticeService(NoticeRepository notices) {
        this.notices = notices;
    }

    public Notice findById(UUID noticeId) {
        return notices.findById(noticeId)
                .orElseThrow(() -> new NoSuchElementException("no notice with id " + noticeId));
    }
}
