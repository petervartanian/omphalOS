WITH src AS (
  SELECT * FROM {{ source('warehouse', 'registry') }}
)
SELECT
  entity_id,
  UPPER(TRIM(entity_name)) AS entity_name,
  UPPER(TRIM(country)) AS country
FROM src;
