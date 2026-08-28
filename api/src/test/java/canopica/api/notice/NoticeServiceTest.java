package canopica.api.notice;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.api.AbstractPostgresTest;
import canopica.api.CaseFixtures;
import canopica.api.determination.DeterminationService;
import java.time.LocalDate;
import java.util.NoSuchElementException;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Proves {@link Notice}'s JPA mapping actually round-trips a row the Python worker's raw insert
 * leaves behind -- the same real-gap-guarding reason {@code AuditEventType} gained {@code
 * DOCUMENT_CLASSIFIED} in Task 3: nothing in Java writes a {@code notice} row today (the worker
 * does, via {@code correspondence_consumer.py}), so this is the only place a real column-mapping
 * bug (the {@code jsonb validation_result} column especially) would ever surface before Task 6
 * depends on it.
 */
class NoticeServiceTest extends AbstractPostgresTest {

    @Autowired NoticeService notices;
    @Autowired DeterminationService determinations;
    @Autowired JdbcTemplate jdbc;

    @Test
    void readsBackARawInsertedNoticeRowIncludingItsJsonbValidationResult() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determinations.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");
        UUID noticeId = CaseFixtures.insertNotice(jdbc, ids.programRequestId(), determinationId, "APPROVAL");

        Notice notice = notices.findById(noticeId);

        assertThat(notice.getProgramRequestId()).isEqualTo(ids.programRequestId());
        assertThat(notice.getDeterminationId()).isEqualTo(determinationId);
        assertThat(notice.getNoticeType()).isEqualTo("APPROVAL");
        assertThat(notice.getStatus()).isEqualTo("DRAFT");
        assertThat(notice.getContent()).isEqualTo("test notice content");
        // jsonb's own canonical text form (key order, spacing) is Postgres's, not this literal's --
        // asserting against it rather than the raw insert string.
        assertThat(notice.getValidationResult()).contains("\"passed\": true");
        assertThat(notice.getGenerationModel()).isEqualTo("llama3.2:3b");
        assertThat(notice.getApprovedBy()).isNull();
        assertThat(notice.getSentAt()).isNull();
    }

    @Test
    void throwsForAnUnknownNoticeId() {
        assertThatThrownBy(() -> notices.findById(UUID.randomUUID()))
                .isInstanceOf(NoSuchElementException.class);
    }
}
