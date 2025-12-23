WITH src AS (
  SELECT * FROM {{ source('warehouse', 'entity_matches') }}
)
SELECT
  shipment_id,
  entity_id,
  CAST(score AS DOUBLE) AS score,
  status,
  explanation
FROM src;
