SELECT
  r.entity_id,
  r.entity_name,
  r.country,
  es.shipment_count,
  es.total_value_usd,
  es.chokepoint_score
FROM registry r
LEFT JOIN entity_scores es ON es.entity_id = r.entity_id
WHERE r.entity_id = :entity_id;
