package ies.portal.caseload;

import static org.assertj.core.api.Assertions.assertThat;

import ies.portal.AbstractPostgresTest;
import ies.portal.CaseFixtures;
import ies.portal.domain.CaseAssignment;
import ies.portal.repo.CaseAssignmentRepository;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class CaseAssignmentServiceTest extends AbstractPostgresTest {

    @Autowired CaseAssignmentService service;
    @Autowired CaseAssignmentRepository caseAssignments;
    @Autowired JdbcTemplate jdbc;

    @Test
    void firstTouchClaimsAnUnassignedHouseholdForTheViewingWorker() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID workerId = CaseFixtures.insertWorker(jdbc, "First Worker", "WORKER");

        CaseAssignment assignment = service.assignOnFirstTouch(ids.householdId(), workerId);

        assertThat(assignment.getWorkerId()).isEqualTo(workerId);
        assertThat(service.isAssignedTo(ids.householdId(), workerId)).isTrue();
    }

    @Test
    void aSecondDifferentWorkerTouchingAnAlreadyAssignedHouseholdDoesNotReplaceTheFirstClaim() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID firstWorkerId = CaseFixtures.insertWorker(jdbc, "First Worker", "WORKER");
        UUID secondWorkerId = CaseFixtures.insertWorker(jdbc, "Second Worker", "WORKER");

        service.assignOnFirstTouch(ids.householdId(), firstWorkerId);
        CaseAssignment secondTouch = service.assignOnFirstTouch(ids.householdId(), secondWorkerId);

        assertThat(secondTouch.getWorkerId()).isEqualTo(firstWorkerId);
        assertThat(service.isAssignedTo(ids.householdId(), firstWorkerId)).isTrue();
        assertThat(service.isAssignedTo(ids.householdId(), secondWorkerId)).isFalse();
        assertThat(countAssignmentsFor(ids.householdId())).isEqualTo(1);
    }

    @Test
    void reassignmentEndsTheOldAssignmentAndStartsANewOneEffectiveDated() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID originalWorkerId = CaseFixtures.insertWorker(jdbc, "Original Worker", "WORKER");
        UUID newWorkerId = CaseFixtures.insertWorker(jdbc, "New Worker", "WORKER");
        CaseAssignment original = service.assignOnFirstTouch(ids.householdId(), originalWorkerId);

        CaseAssignment reassigned = service.reassign(ids.householdId(), newWorkerId);

        assertThat(reassigned.getWorkerId()).isEqualTo(newWorkerId);
        assertThat(service.isAssignedTo(ids.householdId(), newWorkerId)).isTrue();
        assertThat(service.isAssignedTo(ids.householdId(), originalWorkerId)).isFalse();
        assertThat(caseAssignments.findById(original.getId()).orElseThrow().getEffectiveTo()).isNotNull();
        assertThat(countAssignmentsFor(ids.householdId())).isEqualTo(2);
    }

    @Test
    void aHouseholdWithNoAssignmentIsNotAssignedToAnyone() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID someWorkerId = CaseFixtures.insertWorker(jdbc, "Nobody Yet", "WORKER");

        assertThat(service.isAssignedTo(ids.householdId(), someWorkerId)).isFalse();
    }

    private int countAssignmentsFor(UUID householdId) {
        return jdbc.queryForObject(
                "select count(*) from case_assignment where household_id = ?", Integer.class, householdId);
    }
}
