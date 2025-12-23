WITH s AS (
  SELECT * FROM {{ ref('mart_entity_scores') }}
),
ranked AS (
  SELECT
    country,
    entity_id,
    entity_name,
    shipment_count,
    total_value_usd,
    chokepoint_score,
    ROW_NUMBER() OVER (PARTITION BY country ORDER BY chokepoint_score DESC, total_value_usd DESC) AS rk
  FROM s
)
SELECT *
FROM ranked
WHERE rk <= 50;
