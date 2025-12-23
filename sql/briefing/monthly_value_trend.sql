WITH tf AS (
  SELECT SUBSTR(ship_date, 1, 7) AS ship_month, value_usd FROM trade_feed
)
SELECT
  ship_month,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd
FROM tf
GROUP BY ship_month
ORDER BY ship_month;
