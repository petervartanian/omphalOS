SELECT shipment_id, COUNT(*) AS c
FROM trade_feed
GROUP BY shipment_id
HAVING COUNT(*) > 1;
