-- Mart: shipment-level view with best-match entity attribution
with tf as (select * from {{ ref('stg_trade_feed') }}),
em as (
  select
    shipment_id,
    entity_id,
    score,
    status,
    explanation,
    row_number() over (partition by shipment_id order by score desc, entity_id asc) as rn
  from {{ ref('stg_entity_matches') }}
),
best as (
  select * from em where rn = 1
),
reg as (select * from {{ ref('stg_registry') }})
select
  tf.shipment_id,
  tf.exporter_name,
  tf.importer_name,
  tf.country as shipment_country,
  tf.hs_code,
  tf.value_usd,
  tf.ship_date,
  best.entity_id,
  reg.entity_name,
  reg.country as entity_country,
  best.score as match_score,
  best.status as match_status,
  best.explanation
from tf
left join best on best.shipment_id = tf.shipment_id
left join reg on reg.entity_id = best.entity_id
