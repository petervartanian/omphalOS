WITH tf AS (
  SELECT
    UPPER(TRIM(exporter_name)) AS exporter_name,
    COALESCE(exporter_country, country) AS exporter_country,
    SUBSTR(hs_code, 1, 2) AS hs2,
    value_usd,
    ship_date
  FROM trade_feed
)
SELECT
  exporter_name,
  exporter_country,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd,
  MIN(ship_date) AS first_ship_date,
  MAX(ship_date) AS last_ship_date
FROM tf
WHERE exporter_name = UPPER(TRIM(:exporter_name))
GROUP BY exporter_name, exporter_country;
