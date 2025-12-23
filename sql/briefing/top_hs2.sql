WITH tf AS (
  SELECT SUBSTR(hs_code, 1, 2) AS hs2, value_usd FROM trade_feed
)
SELECT
  hs2,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd
FROM tf
GROUP BY hs2
ORDER BY total_value_usd DESC, shipment_count DESC
LIMIT 100;
