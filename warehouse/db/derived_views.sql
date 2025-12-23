CREATE VIEW IF NOT EXISTS v_trade_feed_enriched AS
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

CREATE VIEW IF NOT EXISTS v_entity_exposure AS
SELECT
  em.entity_id,
  r.entity_name,
  r.country,
  COUNT(DISTINCT tf.shipment_id) AS shipment_count,
  SUM(tf.value_usd) AS total_value_usd,
  AVG(em.score) AS mean_match_score,
  SUM(CASE WHEN em.status = 'MATCH' THEN 1 ELSE 0 END) AS matched_shipments
FROM entity_matches em
JOIN v_trade_feed_enriched tf ON tf.shipment_id = em.shipment_id
LEFT JOIN registry r ON r.entity_id = em.entity_id
GROUP BY em.entity_id, r.entity_name, r.country;

CREATE VIEW IF NOT EXISTS v_hs2_exposure AS
SELECT
  hs2,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd
FROM v_trade_feed_enriched
GROUP BY hs2;

CREATE VIEW IF NOT EXISTS v_exporter_monthly AS
SELECT
  exporter_name,
  exporter_country,
  ship_month,
  COUNT(*) AS shipment_count,
  SUM(value_usd) AS total_value_usd
FROM v_trade_feed_enriched
GROUP BY exporter_name, exporter_country, ship_month;
