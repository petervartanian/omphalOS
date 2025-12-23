WITH tf AS (
  SELECT * FROM (SELECT * FROM trade_feed)
),
m AS (
  SELECT * FROM entity_matches
),
r AS (
  SELECT * FROM registry
)
SELECT
  m.entity_id,
  MAX(r.entity_name) AS entity_name,
  MAX(r.country) AS country,
  COUNT(DISTINCT tf.shipment_id) AS shipment_count,
  SUM(tf.value_usd) AS total_value_usd,
  AVG(m.score) AS mean_match_score,
  SUM(CASE WHEN m.status = 'MATCH' THEN 1 ELSE 0 END) AS matched_shipments
FROM m
JOIN tf ON tf.shipment_id = m.shipment_id
LEFT JOIN r ON r.entity_id = m.entity_id
GROUP BY m.entity_id;
