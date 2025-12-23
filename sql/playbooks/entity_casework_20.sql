BEGIN;

WITH params AS (
  SELECT
    :entity_id AS entity_id,
    CAST(:min_score AS DOUBLE) AS min_score,
    CAST(:min_value AS DOUBLE) AS min_value,
    CAST(:limit AS INTEGER) AS limit_rows
),
entity AS (
  SELECT r.entity_id, r.entity_name, r.country
  FROM registry r
  JOIN params p ON p.entity_id = r.entity_id
),
matches AS (
  SELECT m.shipment_id, m.entity_id, m.score, m.status, m.explanation
  FROM entity_matches m
  JOIN params p ON p.entity_id = m.entity_id
  WHERE m.score >= (SELECT min_score FROM params)
),
shipments AS (
  SELECT
    tf.shipment_id,
    tf.exporter_name,
    tf.importer_name,
    COALESCE(tf.exporter_country, tf.country) AS exporter_country,
    COALESCE(tf.importer_country, tf.country) AS importer_country,
    tf.hs_code,
    SUBSTR(tf.hs_code, 1, 2) AS hs2,
    SUBSTR(tf.hs_code, 1, 4) AS hs4,
    SUBSTR(tf.hs_code, 1, 6) AS hs6,
    tf.value_usd,
    tf.ship_date,
    SUBSTR(tf.ship_date, 1, 7) AS ship_month
  FROM trade_feed tf
  JOIN matches m ON m.shipment_id = tf.shipment_id
  WHERE tf.value_usd >= (SELECT min_value FROM params)
),
scoped AS (
  SELECT
    s.*,
    m.score,
    m.status,
    m.explanation
  FROM shipments s
  JOIN matches m ON m.shipment_id = s.shipment_id
)
SELECT
  (SELECT entity_id FROM entity) AS entity_id,
  (SELECT entity_name FROM entity) AS entity_name,
  (SELECT country FROM entity) AS entity_country,
  scoped.*
FROM scoped
ORDER BY scoped.value_usd DESC, scoped.score DESC
LIMIT (SELECT limit_rows FROM params);

WITH hs_profile AS (
  SELECT
    hs2,
    hs4,
    hs6,
    COUNT(*) AS shipment_count,
    SUM(value_usd) AS total_value_usd,
    AVG(score) AS mean_match_score
  FROM scoped
  GROUP BY hs2, hs4, hs6
)
SELECT *
FROM hs_profile
ORDER BY total_value_usd DESC, shipment_count DESC
LIMIT (SELECT limit_rows FROM params);

WITH counterparties AS (
  SELECT
    exporter_name,
    exporter_country,
    importer_name,
    importer_country,
    COUNT(*) AS shipment_count,
    SUM(value_usd) AS total_value_usd,
    AVG(score) AS mean_match_score
  FROM scoped
  GROUP BY exporter_name, exporter_country, importer_name, importer_country
)
SELECT *
FROM counterparties
ORDER BY total_value_usd DESC, shipment_count DESC
LIMIT (SELECT limit_rows FROM params);

WITH monthly AS (
  SELECT
    ship_month,
    COUNT(*) AS shipment_count,
    SUM(value_usd) AS total_value_usd,
    AVG(score) AS mean_match_score
  FROM scoped
  GROUP BY ship_month
)
SELECT *
FROM monthly
ORDER BY ship_month;

ROLLBACK;
