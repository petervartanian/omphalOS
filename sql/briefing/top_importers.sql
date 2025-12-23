WITH tf AS (
  SELECT
    UPPER(TRIM(importer_name)) AS importer_name,
    COALESCE(importer_country, country) AS importer_country,
    value_usd
  FROM trade_feed
)
SELECT
  importer_name,
  importer_country,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd
FROM tf
GROUP BY importer_name, importer_country
ORDER BY total_value_usd DESC, shipment_count DESC
LIMIT 100;
