package canopica.api.caseload;

import canopica.api.api.dto.AtRiskCaseResponse;
import java.sql.Timestamp;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * The Case SLA/Compliance Monitor's live at-risk-case query (Phase 4 Task 6, design doc §2.4). Deliberately
 * operational, not a mart -- same-day currency is the entire point, which a nightly dbt build structurally
 * can't give -- so this ages {@code program_request} directly against SNAP's 7-day-expedited/30-day standard,
 * the same standard {@code mart_processing_timeliness.sql} applies to already-decided cases and {@code
 * ai/sla_monitor/prioritize.py} independently re-derives for its own batch refresh: three implementations of
 * the same rule in three languages, cross-checked by their own tests rather than shared via a library, the
 * same deliberate duplication this project's dbt/Java split already accepts elsewhere. {@code stallReason}
 * is a plain left join to {@code sla_stall_reason}, never computed here -- see that table's own migration
 * comment for why the write side lives in {@code ai/sla_monitor}, not this class.
 */
@Component
public class AtRiskCaseQuery {

    private final JdbcTemplate jdbc;

    AtRiskCaseQuery(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<AtRiskCaseResponse> findAtRiskCases() {
        return jdbc.query(
                """
                select pr.id as program_request_id, pr.requested_on, pr.is_expedited,
                       p.first_name || ' ' || p.last_name as household_head_name,
                       (case when pr.is_expedited then 7 else 30 end)
                           - (current_date - pr.requested_on) as days_remaining,
                       sr.reason as stall_reason, sr.generated_at as stall_reason_generated_at
                from program_request pr
                join application a on a.id = pr.application_id
                join household h on h.id = a.household_id
                join person p on p.id = h.head_person_id
                left join sla_stall_reason sr on sr.program_request_id = pr.id
                where pr.status in ('SUBMITTED', 'PENDING_VERIFICATION')
                order by days_remaining asc
                """,
                (rs, rowNum) -> {
                    Timestamp generatedAt = rs.getTimestamp("stall_reason_generated_at");
                    return new AtRiskCaseResponse(
                            (UUID) rs.getObject("program_request_id"),
                            rs.getString("household_head_name"),
                            rs.getDate("requested_on").toLocalDate(),
                            rs.getBoolean("is_expedited"),
                            rs.getInt("days_remaining"),
                            rs.getString("stall_reason"),
                            generatedAt == null ? null : generatedAt.toInstant());
                });
    }
}
