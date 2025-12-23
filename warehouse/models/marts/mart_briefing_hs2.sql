WITH t AS (
  SELECT * FROM {{ ref('stg_trade_feed') }}
)
SELECT
  hs2,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd
FROM t
GROUP BY hs2
ORDER BY total_value_usd DESC, shipment_count DESC
LIMIT 100;
