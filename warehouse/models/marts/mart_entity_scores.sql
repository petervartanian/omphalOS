WITH base AS (
  SELECT * FROM {{ ref('int_entity_exposure') }}
),
scored AS (
  SELECT
    entity_id,
    entity_name,
    country,
    shipment_count,
    total_value_usd,
    mean_match_score,
    matched_shipments,
    CASE
      WHEN shipment_count = 0 THEN 0.0
      ELSE CAST(matched_shipments AS DOUBLE) / CAST(shipment_count AS DOUBLE)
    END AS match_rate,
    CASE
      WHEN total_value_usd IS NULL THEN 0.0
      ELSE total_value_usd
    END AS value_signal
  FROM base
)
SELECT
  entity_id,
  entity_name,
  country,
  shipment_count,
  total_value_usd,
  (value_signal * mean_match_score * match_rate) AS chokepoint_score,
  mean_match_score,
  match_rate
FROM scored;
