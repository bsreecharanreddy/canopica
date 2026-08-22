-- Fails if a gold model exposes a column whose name matches a PII shape
-- (macros/is_pii_column.sql). Applied to every gold model in gold.yml.
{% test no_pii_in_gold(model) %}
    with offending as (
        select column_name
        from information_schema.columns
        where table_name = '{{ model.identifier }}'
          and ({{ is_pii_column('column_name') }})
    )
    select * from offending
{% endtest %}
