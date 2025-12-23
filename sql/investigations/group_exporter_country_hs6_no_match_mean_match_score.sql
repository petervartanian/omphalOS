WITH tf AS (
  SELECT
    shipment_id,
    exporter_name,
    importer_name,
    COALESCE(exporter_country, country) AS exporter_country,
    COALESCE(importer_country, country) AS importer_country,
    SUBSTR(hs_code, 1, 2) AS hs2,
    SUBSTR(hs_code, 1, 4) AS hs4,
    SUBSTR(hs_code, 1, 6) AS hs6,
    value_usd,
    ship_date,
    SUBSTR(ship_date, 1, 7) AS ship_month,
    SUBSTR(ship_date, 1, 4) AS ship_year
  FROM trade_feed
),
m AS (
  SELECT shipment_id, entity_id, score, status FROM entity_matches
),
j AS (
  SELECT tf.*, m.entity_id, m.score, m.status
  FROM tf
  JOIN m ON m.shipment_id = tf.shipment_id
)
SELECT
  exporter_country AS exporter_country,
  hs6 AS hs6,
  AVG(score) AS mean_match_score,
  COUNT(*) AS row_count
FROM j
WHERE status = 'NO_MATCH'
GROUP BY exporter_country, hs6
ORDER BY mean_match_score DESC, row_count DESC
LIMIT :limit;
