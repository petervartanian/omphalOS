SELECT
  entity_id,
  entity_name,
  country,
  shipment_count,
  total_value_usd,
  chokepoint_score
FROM entity_scores
ORDER BY chokepoint_score DESC, total_value_usd DESC
LIMIT 50;
