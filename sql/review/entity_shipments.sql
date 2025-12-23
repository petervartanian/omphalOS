WITH tf AS (
  SELECT * FROM trade_feed
),
m AS (
  SELECT * FROM entity_matches WHERE entity_id = :entity_id
)
SELECT
  tf.shipment_id,
  tf.exporter_name,
  tf.importer_name,
  COALESCE(tf.exporter_country, tf.country) AS exporter_country,
  COALESCE(tf.importer_country, tf.country) AS importer_country,
  tf.hs_code,
  tf.value_usd,
  tf.ship_date,
  m.score,
  m.status,
  m.explanation
FROM tf
JOIN m ON m.shipment_id = tf.shipment_id
ORDER BY tf.value_usd DESC, m.score DESC
LIMIT 500;
