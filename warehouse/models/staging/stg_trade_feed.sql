-- Staging: trade_feed
-- The reference pipeline writes a table named `trade_feed` into the run warehouse.
-- This model exists so downstream marts never select directly from a raw table.

select
  shipment_id,
  exporter_name,
  importer_name,
  country,
  hs_code,
  cast(value_usd as double) as value_usd,
  ship_date
from {{ source('raw', 'trade_feed') }}
