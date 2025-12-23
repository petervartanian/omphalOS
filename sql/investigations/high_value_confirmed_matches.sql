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
    hs_code,
    value_usd,
    ship_date,
    SUBSTR(ship_date, 1, 7) AS ship_month
  FROM trade_feed
),
m AS (
  SELECT * FROM entity_matches
)
SELECT
  tf.shipment_id,
  tf.exporter_name,
  tf.importer_name,
  tf.exporter_country,
  tf.importer_country,
  tf.hs2,
  tf.hs4,
  tf.hs6,
  tf.hs_code,
  tf.value_usd,
  tf.ship_date,
  m.entity_id,
  m.score,
  m.status
FROM tf
JOIN m ON m.shipment_id = tf.shipment_id
WHERE m.status = 'MATCH'
  AND m.score >= :min_score
  AND tf.value_usd >= :min_value
ORDER BY tf.value_usd DESC, m.score DESC
LIMIT :limit;
