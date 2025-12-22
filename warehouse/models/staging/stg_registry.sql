-- Staging: registry
select
  entity_id,
  entity_name,
  country
from {{ source('raw', 'registry') }}
