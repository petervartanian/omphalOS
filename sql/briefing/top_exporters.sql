WITH tf AS (
  SELECT
    UPPER(TRIM(exporter_name)) AS exporter_name,
    COALESCE(exporter_country, country) AS exporter_country,
    value_usd
  FROM trade_feed
)
SELECT
  exporter_name,
  exporter_country,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd
FROM tf
GROUP BY exporter_name, exporter_country
ORDER BY total_value_usd DESC, shipment_count DESC
LIMIT 100;
