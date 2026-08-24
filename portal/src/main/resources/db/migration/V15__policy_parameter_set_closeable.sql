-- Narrows V3's blanket immutability by exactly one case, so that a
-- superseding parameter set can close the one it supersedes. Full reasoning:
-- docs/design/2026-08-23-policy-parameter-supersession.md.
--
-- Why this is safe, in one line: re-deriving an old determination resolves
-- by parameter-set *id* (PolicyParameterResolver.resolveSnapByParameterSetId)
-- and reads only policy_parameter values -- it never reads effective_from or
-- effective_to, so neither date column participates in the roadmap §3.5
-- reproducibility guarantee. What that guarantee actually rests on is that a
-- published figure never changes and a set never loses its identity, and both
-- stay absolutely enforced below.
--
-- The permitted edit is one-way and one-shot. null -> a date is allowed; a
-- date -> anything (including back to null) is not, so a closed range can
-- never be reopened or slid. And it is total on every other column: a close
-- that carries any other edit along with it is refused, which is what stops
-- this from being a general-purpose UPDATE hole wearing an effective_to hat.

-- V3 pointed both triggers at one shared function. That stops working the
-- moment the two tables need different rules: PL/pgSQL plans a whole boolean
-- expression up front rather than short-circuiting it, so a single function
-- referencing OLD.effective_to fails with `record "old" has no field
-- "effective_to"` when fired for policy_parameter -- which has no such
-- column -- no matter how the condition is ordered or guarded on
-- tg_table_name. Splitting into one function per table is both the fix and
-- the better shape: each says only what its own table's rule is, and neither
-- can be broken by a column the other one grows.
create or replace function policy_parameter_is_immutable() returns trigger
language plpgsql as $$
begin
    raise exception 'policy_parameter rows are immutable once published (attempted %)', tg_op;
end;
$$;

drop trigger policy_parameter_no_mutation on policy_parameter;

create trigger policy_parameter_no_mutation
    before update or delete on policy_parameter
    for each row execute function policy_parameter_is_immutable();

-- The set's own rule, narrowed. policy_parameter above keeps the blanket
-- refusal: a published *figure* is still absolutely immutable, which is the
-- half the reproducibility guarantee actually rests on.
create or replace function policy_parameter_set_is_immutable() returns trigger
language plpgsql as $$
begin
    if tg_op = 'UPDATE'
       and old.effective_to is null
       and new.effective_to is not null
       and (new.id, new.program_code, new.version_label, new.effective_from,
            new.source_citation, new.retrieved_on, new.published_at)
           is not distinct from
           (old.id, old.program_code, old.version_label, old.effective_from,
            old.source_citation, old.retrieved_on, old.published_at)
    then
        return new;
    end if;
    raise exception 'policy_parameter_set rows are immutable once published (attempted %)', tg_op;
end;
$$;
