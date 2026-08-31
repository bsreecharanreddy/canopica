{#
    A name-based PII shape check, deliberately blunt: it cannot be argued
    with, and a real, intentional exception has to be written down (as a
    disable/exclude on the test) rather than reasoned around inline.
    Shared between any future gold-layer gate, not just no_pii_in_gold.

    Phase 5 Task 1's real Databricks run found SIMILAR TO doesn't port --
    it's DuckDB/Postgres-standard SQL, not recognized by Databricks SQL at
    all (a genuine parser syntax error, not a behavior difference). RLIKE
    is Databricks/Spark's equivalent and needs no %...% wrapping, since
    RLIKE already matches anywhere in the string (SIMILAR TO's %...% was
    only there for its own full-string-match semantics).
#}
{% macro is_pii_column(column_name) -%}
{%- if target.type == 'databricks' -%}
lower({{ column_name }}) rlike
    '(ssn|social_security|first_name|last_name|full_name|email|phone|date_of_birth|dob|street|address)'
{%- else -%}
lower({{ column_name }}) similar to
    '%(ssn|social_security|first_name|last_name|full_name|email|phone|date_of_birth|dob|street|address)%'
{%- endif -%}
{%- endmacro %}
