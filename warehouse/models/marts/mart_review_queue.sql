WITH scores AS (
  SELECT * FROM {{ ref('mart_entity_scores') }}
),
ranked AS (
  SELECT
    entity_id,
    entity_name,
    country,
    shipment_count,
    total_value_usd,
    chokepoint_score,
    ROW_NUMBER() OVER (ORDER BY chokepoint_score DESC, total_value_usd DESC) AS rk
  FROM scores
)
SELECT
  CAST(rk AS TEXT) AS review_id,
  CURRENT_TIMESTAMP AS created_at,
  entity_id,
  entity_name,
  country,
  chokepoint_score AS severity,
  'Ranked by chokepoint_score; tie-break by total_value_usd.' AS rationale,
  '{"source":"warehouse","model":"mart_review_queue"}' AS payload_json
FROM ranked
WHERE rk <= 250;
