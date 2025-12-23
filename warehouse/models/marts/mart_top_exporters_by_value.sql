WITH t AS (
  SELECT * FROM { ref('stg_trade_feed') }
)
SELECT
  exporter_name,
  exporter_country,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd
FROM t
GROUP BY exporter_name, exporter_country
ORDER BY SUM(value_usd) DESC, shipment_count DESC
LIMIT 200;
