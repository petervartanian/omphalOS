{% macro safe_divide(numerator, denominator) -%}
CASE
  WHEN {{ denominator }} IS NULL THEN 0.0
  WHEN {{ denominator }} = 0 THEN 0.0
  ELSE CAST({{ numerator }} AS DOUBLE) / CAST({{ denominator }} AS DOUBLE)
END
{%- endmacro %}