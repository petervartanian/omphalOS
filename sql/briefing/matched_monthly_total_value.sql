WITH tf AS (
  SELECT shipment_id, value_usd, SUBSTR(ship_date, 1, 7) AS ship_month FROM trade_feed
),
m AS (
  SELECT shipment_id, status FROM entity_matches
),
j AS (
  SELECT tf.ship_month, tf.value_usd
  FROM tf
  JOIN m ON m.shipment_id = tf.shipment_id
  WHERE m.status = 'MATCH'
)
SELECT
  ship_month,
  COUNT(*) AS matched_shipments,
  SUM(value_usd) AS matched_total_value_usd,
  AVG(value_usd) AS matched_mean_value_usd
FROM j
GROUP BY ship_month
ORDER BY ship_month;
