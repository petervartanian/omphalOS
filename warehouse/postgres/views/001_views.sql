CREATE OR REPLACE VIEW omphalos.v_trade_enriched AS
SELECT
  shipment_id,
  exporter_name,
  importer_name,
  exporter_country,
  importer_country,
  hs_code,
  hs2,
  hs4,
  hs6,
  value_usd,
  ship_date,
  run_id
FROM omphalos.trade_feed;

CREATE OR REPLACE VIEW omphalos.v_entity_scores_ranked AS
SELECT
  entity_id,
  entity_name,
  country,
  shipment_count,
  total_value_usd,
  chokepoint_score,
  dense_rank() OVER (PARTITION BY run_id ORDER BY chokepoint_score DESC, total_value_usd DESC) AS risk_rank,
  run_id
FROM omphalos.entity_scores;

CREATE OR REPLACE VIEW omphalos.v_review_queue_flat AS
SELECT
  q.run_id,
  q.shipment_id,
  q.entity_id,
  r.entity_name,
  q.review_status,
  q.severity,
  q.rationale,
  t.exporter_name,
  t.importer_name,
  t.exporter_country,
  t.importer_country,
  t.hs_code,
  t.value_usd,
  t.ship_date
FROM omphalos.review_queue q
JOIN omphalos.registry r ON r.entity_id = q.entity_id
JOIN omphalos.trade_feed t ON t.shipment_id = q.shipment_id;
