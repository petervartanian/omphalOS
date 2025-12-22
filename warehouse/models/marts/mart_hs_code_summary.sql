-- Mart: HS code summary
select
  hs_code,
  count(*) as shipment_count,
  sum(value_usd) as total_value_usd,
  avg(value_usd) as avg_value_usd
from {{ ref('mart_shipments_by_entity') }}
group by hs_code
order by total_value_usd desc
