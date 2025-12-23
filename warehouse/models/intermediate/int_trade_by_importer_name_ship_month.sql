WITH t AS (
  SELECT * FROM { ref('stg_trade_feed') }
)
SELECT
  importer_name,
  ship_month,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd,
  MIN(value_usd) AS min_value_usd,
  MAX(value_usd) AS max_value_usd
FROM t
GROUP BY importer_name, ship_month;
