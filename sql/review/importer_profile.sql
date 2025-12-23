WITH tf AS (
  SELECT
    UPPER(TRIM(importer_name)) AS importer_name,
    COALESCE(importer_country, country) AS importer_country,
    SUBSTR(hs_code, 1, 2) AS hs2,
    value_usd,
    ship_date
  FROM trade_feed
)
SELECT
  importer_name,
  importer_country,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd,
  AVG(value_usd) AS mean_value_usd,
  MIN(ship_date) AS first_ship_date,
  MAX(ship_date) AS last_ship_date
FROM tf
WHERE importer_name = UPPER(TRIM(:importer_name))
GROUP BY importer_name, importer_country;
