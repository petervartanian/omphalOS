WITH tf AS (
  SELECT
    COALESCE(exporter_country, country) AS exporter_country,
    COALESCE(importer_country, country) AS importer_country,
    SUBSTR(hs_code, 1, 2) AS hs2,
    SUBSTR(hs_code, 1, 4) AS hs4,
    SUBSTR(hs_code, 1, 6) AS hs6,
    SUBSTR(ship_date, 1, 7) AS ship_month,
    value_usd,
    shipment_id
  FROM trade_feed
),
m AS (
  SELECT shipment_id, entity_id, score, status FROM entity_matches
  WHERE status = 'MATCH' AND score >= :min_score
),
j AS (
  SELECT tf.*, m.entity_id, m.score
  FROM tf
  JOIN m ON m.shipment_id = tf.shipment_id
)
SELECT
  tf.importer_country AS importer_country,
  tf.hs6 AS hs6,
  COUNT(*) AS matched_shipments,
  SUM(value_usd) AS matched_total_value_usd,
  AVG(score) AS mean_match_score,
  AVG(value_usd) AS mean_value_usd
FROM j
GROUP BY tf.importer_country, tf.hs6
ORDER BY matched_total_value_usd DESC, matched_shipments DESC
LIMIT :limit;
