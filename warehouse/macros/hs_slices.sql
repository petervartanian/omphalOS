{% macro hs2(expr) -%}
SUBSTR({{ expr }}, 1, 2)
{%- endmacro %}

{% macro hs4(expr) -%}
SUBSTR({{ expr }}, 1, 4)
{%- endmacro %}

{% macro hs6(expr) -%}
SUBSTR({{ expr }}, 1, 6)
{%- endmacro %}