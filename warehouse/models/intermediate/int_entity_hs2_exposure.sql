WITH m AS (
  SELECT * FROM {{ ref('stg_entity_matches') }}
),
t AS (
  SELECT * FROM {{ ref('stg_trade_feed') }}
),
reg AS (
  SELECT * FROM {{ ref('stg_registry') }}
),
j AS (
  SELECT
    m.entity_id,
    r.entity_name,
    r.country,
    t.hs2,
    t.ship_month,
    t.value_usd,
    m.score,
    m.status
  FROM m
  JOIN t ON t.shipment_id = m.shipment_id
  LEFT JOIN reg r ON r.entity_id = m.entity_id
)
SELECT
  entity_id,
  MAX(entity_name) AS entity_name,
  MAX(country) AS country,
  hs2,
  ship_month,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(score) AS mean_match_score,
  SUM(CASE WHEN status = 'MATCH' THEN 1 ELSE 0 END) AS matched_shipments
FROM j
GROUP BY entity_id, hs2, ship_month;
