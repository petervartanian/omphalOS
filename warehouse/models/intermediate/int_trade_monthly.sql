WITH t AS (
  SELECT * FROM {{ ref('stg_trade_feed') }}
)
SELECT
  ship_month,
  exporter_name,
  exporter_country,
  importer_name,
  importer_country,
  hs2,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd
FROM t
GROUP BY ship_month, exporter_name, exporter_country, importer_name, importer_country, hs2;
