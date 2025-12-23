WITH e AS (
  SELECT * FROM {{ ref('int_entity_hs2_exposure') }}
),
scored AS (
  SELECT
    entity_id,
    entity_name,
    country,
    hs2,
    ship_month,
    shipment_count,
    total_value_usd,
    mean_match_score,
    {{ safe_divide('matched_shipments', 'shipment_count') }} AS match_rate,
    (total_value_usd * mean_match_score * {{ safe_divide('matched_shipments', 'shipment_count') }}) AS exposure_score
  FROM e
)
SELECT * FROM scored;
