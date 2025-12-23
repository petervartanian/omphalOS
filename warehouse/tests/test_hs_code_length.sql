SELECT shipment_id
FROM {{ ref('stg_trade_feed') }}
WHERE hs_code IS NULL OR LENGTH(hs_code) < 6;
