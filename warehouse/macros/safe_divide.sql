{% macro safe_divide(numerator, denominator) -%}
case
  when {{ denominator }} is null then null
  when {{ denominator }} = 0 then null
  else ({{ numerator }} * 1.0) / {{ denominator }}
end
{%- endmacro %}

