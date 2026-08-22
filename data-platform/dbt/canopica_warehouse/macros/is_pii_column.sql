{#
    A name-based PII shape check, deliberately blunt: it cannot be argued
    with, and a real, intentional exception has to be written down (as a
    disable/exclude on the test) rather than reasoned around inline.
    Shared between any future gold-layer gate, not just no_pii_in_gold.
#}
{% macro is_pii_column(column_name) -%}
lower({{ column_name }}) similar to
    '%(ssn|social_security|first_name|last_name|full_name|email|phone|date_of_birth|dob|street|address)%'
{%- endmacro %}
