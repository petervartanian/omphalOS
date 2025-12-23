WITH j AS (
  SELECT
    tf.shipment_id,
    tf.exporter_name,
    tf.importer_name,
    COALESCE(tf.exporter_country, tf.country) AS exporter_country,
    COALESCE(tf.importer_country, tf.country) AS importer_country,
    SUBSTR(tf.hs_code, 1, 6) AS hs6,
    tf.value_usd,
    tf.ship_date,
    m.entity_id,
    m.score,
    m.status,
    NTILE(100) OVER (ORDER BY tf.value_usd) AS value_pct
  FROM trade_feed tf
  JOIN entity_matches m ON m.shipment_id = tf.shipment_id
  WHERE m.status = 'NO_MATCH'
)
SELECT *
FROM j
WHERE value_pct >= :pctile
ORDER BY value_usd DESC
LIMIT :limit;
