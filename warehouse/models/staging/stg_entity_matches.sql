-- Staging: entity_matches
select
  shipment_id,
  entity_id,
  cast(score as double) as score,
  status,
  explanation
from {{ source('raw', 'entity_matches') }}
