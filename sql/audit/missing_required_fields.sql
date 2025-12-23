SELECT shipment_id
FROM trade_feed
WHERE exporter_name IS NULL
   OR importer_name IS NULL
   OR hs_code IS NULL
   OR value_usd IS NULL
   OR ship_date IS NULL;
