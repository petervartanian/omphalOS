WITH tf AS (
  SELECT
    COALESCE(exporter_country, country) AS exporter_country,
    COALESCE(importer_country, country) AS importer_country,
    SUBSTR(hs_code, 1, 2) AS hs2,
    value_usd,
    ship_date
  FROM trade_feed
)
SELECT
  exporter_country,
  importer_country,
  hs2,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd
FROM tf
WHERE exporter_country = :exporter_country
  AND importer_country = :importer_country
  AND hs2 = :hs2
GROUP BY exporter_country, importer_country, hs2;
