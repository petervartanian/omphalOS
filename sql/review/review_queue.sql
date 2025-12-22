-- Review queue: shipments that require human review
-- Parameters: none
select
  tf.shipment_id,
  tf.exporter_name,
  tf.importer_name,
  tf.country as shipment_country,
  tf.hs_code,
  tf.value_usd,
  tf.ship_date,
  em.entity_id,
  r.entity_name,
  r.country as entity_country,
  em.score as match_score,
  em.status as match_status,
  em.explanation
from trade_feed tf
left join entity_matches em on em.shipment_id = tf.shipment_id
left join registry r on r.entity_id = em.entity_id
where em.status = 'REVIEW'
order by em.score desc, tf.value_usd desc;
