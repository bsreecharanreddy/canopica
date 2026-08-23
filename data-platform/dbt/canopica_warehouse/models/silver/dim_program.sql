{{ config(materialized='table') }}

-- Static, not bronze-sourced: no operational `program` table exists yet --
-- program_code is just a check-constrained text column on program_request
-- (today, only 'SNAP'). A real bronze source is Phase 5's job, when domain
-- expansion (Medicaid/TANF) actually adds more than one program to enumerate.
select * from (
    values ('SNAP', 'Supplemental Nutrition Assistance Program', '7 U.S.C. §2011 et seq.')
) as t (program_code, program_name, statutory_citation)
