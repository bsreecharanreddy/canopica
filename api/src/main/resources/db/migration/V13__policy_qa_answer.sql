-- Owned and written by the Python ai/ service (canopica_ai.policy_intelligence.
-- qa.provenance), not the Java portal -- same "Flyway is the one schema
-- authority for canopica_operational regardless of which language owns the
-- table" precedent V11's pii_token already set.
create schema if not exists ai;

create table ai.policy_qa_answer (
    id                      uuid        primary key default gen_random_uuid(),
    question                text        not null,
    answer                  text        not null,
    citations               text[]      not null default '{}',
    abstained               boolean     not null,
    corpus_version          text        not null,
    embedding_model_version text        not null,
    -- top-k and the named search pipeline (RRF rank_constant + rerank model
    -- are versioned by that pipeline's own name, not duplicated here).
    retrieval_config        jsonb       not null,
    prompt_version          text        not null,
    -- Null for an abstained answer: no LLM call was made at all.
    generation_model        text,
    generation_params       jsonb,
    retrieved_chunk_ids     text[]      not null default '{}',
    -- Set only for the "why was I denied" path.
    determination_id        uuid        references eligibility_determination (id),
    created_at              timestamptz not null default now()
);

revoke all on ai.policy_qa_answer from public;
