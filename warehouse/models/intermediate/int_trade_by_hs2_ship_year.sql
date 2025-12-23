WITH t AS (
  SELECT * FROM { ref('stg_trade_feed') }
)
SELECT
  hs2,
  ship_year,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd,
  MIN(value_usd) AS min_value_usd,
  MAX(value_usd) AS max_value_usd
FROM t
GROUP BY hs2, ship_year;
