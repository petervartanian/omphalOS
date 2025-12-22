-- Mart: value exposure by country (shipment country)
select
  shipment_country as country,
  count(*) as shipment_count,
  sum(value_usd) as total_value_usd,
  avg(value_usd) as avg_value_usd
from {{ ref('mart_shipments_by_entity') }}
group by shipment_country
order by total_value_usd desc
