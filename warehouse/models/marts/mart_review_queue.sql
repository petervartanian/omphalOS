-- Mart: review queue (shipments where matching is not automatic)
select
  shipment_id,
  exporter_name,
  importer_name,
  shipment_country,
  hs_code,
  value_usd,
  ship_date,
  entity_id,
  entity_name,
  entity_country,
  match_score,
  match_status,
  explanation
from {{ ref('mart_shipments_by_entity') }}
where coalesce(match_status, '') = 'REVIEW'
order by match_score desc, value_usd desc
