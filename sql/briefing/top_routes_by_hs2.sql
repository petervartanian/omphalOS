WITH tf AS (
  SELECT
    COALESCE(exporter_country, country) AS exporter_country,
    COALESCE(importer_country, country) AS importer_country,
    SUBSTR(hs_code, 1, 2) AS hs2,
    value_usd
  FROM trade_feed
)
SELECT
  exporter_country,
  importer_country,
  hs2,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd
FROM tf
GROUP BY exporter_country, importer_country, hs2
ORDER BY total_value_usd DESC
LIMIT :limit;
