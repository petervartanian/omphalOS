WITH q AS (
  SELECT * FROM {{ ref('mart_review_queue') }}
),
s AS (
  SELECT * FROM {{ ref('mart_entity_scores') }}
)
SELECT
  q.review_id,
  q.created_at,
  s.entity_id,
  s.entity_name,
  s.country,
  s.shipment_count,
  s.total_value_usd,
  s.chokepoint_score
FROM q
JOIN s ON s.entity_id = q.entity_id
ORDER BY CAST(q.review_id AS INTEGER);
