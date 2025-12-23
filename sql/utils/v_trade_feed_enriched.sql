SELECT
  shipment_id,
  exporter_name,
  importer_name,
  COALESCE(exporter_country, country) AS exporter_country,
  COALESCE(importer_country, country) AS importer_country,
  COALESCE(country, exporter_country) AS country,
  hs_code,
  SUBSTR(hs_code, 1, 2) AS hs2,
  SUBSTR(hs_code, 1, 4) AS hs4,
  SUBSTR(hs_code, 1, 6) AS hs6,
  value_usd,
  ship_date,
  SUBSTR(ship_date, 1, 7) AS ship_month,
  SUBSTR(ship_date, 1, 4) AS ship_year
FROM trade_feed;
