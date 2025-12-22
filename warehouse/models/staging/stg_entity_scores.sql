-- Staging: entity_scores (as produced by the reference pipeline)
select
  entity_id,
  entity_name,
  country,
  cast(shipment_count as bigint) as shipment_count,
  cast(total_value_usd as double) as total_value_usd,
  cast(chokepoint_score as double) as chokepoint_score
from {{ source('raw', 'entity_scores') }}
