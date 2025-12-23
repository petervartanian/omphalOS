WITH matches AS (
  SELECT * FROM {{ ref('stg_entity_matches') }}
),
trade AS (
  SELECT * FROM {{ ref('stg_trade_feed') }}
),
reg AS (
  SELECT * FROM {{ ref('stg_registry') }}
),
joined AS (
  SELECT
    m.entity_id,
    r.entity_name,
    r.country,
    t.shipment_id,
    t.value_usd,
    t.ship_date,
    t.ship_month,
    t.ship_year,
    m.score,
    m.status
  FROM matches m
  JOIN trade t ON t.shipment_id = m.shipment_id
  LEFT JOIN reg r ON r.entity_id = m.entity_id
)
SELECT
  entity_id,
  MAX(entity_name) AS entity_name,
  MAX(country) AS country,
  COUNT(DISTINCT shipment_id) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(score) AS mean_match_score,
  SUM(CASE WHEN status = 'MATCH' THEN 1 ELSE 0 END) AS matched_shipments
FROM joined
GROUP BY entity_id;
