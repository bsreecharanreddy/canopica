package canopica.api.repo;

import canopica.api.document.Document;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<Document, UUID> {

    /**
     * The review queue's own source query (Task 4): every {@code CLASSIFIED} document across the caller's
     * caseload, lowest confidence first, per design doc §2.3's "confidence drives prioritization." An empty
     * {@code programRequestIds} is the caller's job to short-circuit -- see {@code DocumentController
     * #reviewQueue}'s own doc for why.
     */
    List<Document> findByProgramRequestIdInAndClassificationStatusOrderByExtractionConfidenceAsc(
            List<UUID> programRequestIds, String classificationStatus);

    // clearAutomatically: DocumentService#confirm reads this same document both before and after this
    // bulk update, inside one @Transactional method -- without clearing the persistence context, Hibernate's
    // first-level cache returns the pre-update entity on the second read (a bulk JPQL update bypasses the
    // managed entity, so it never gets marked dirty). VerificationRepository#updateStatus doesn't need this
    // only because every caller re-reads it in a separate transaction, not within the same method.
    // flushAutomatically: without it, clearAutomatically's entityManager.clear() detaches the IncomeRecord
    // entities confirm() just saved() before Hibernate ever flushes their pending inserts -- a save() that
    // silently never reaches the database. Found by the real regression test below, not by inspection.
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Document d set d.classificationStatus = :status where d.id = :id")
    void updateClassificationStatus(@Param("id") UUID id, @Param("status") String status);
}
