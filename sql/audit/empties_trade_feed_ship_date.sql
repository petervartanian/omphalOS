SELECT COUNT(*) AS empty_count FROM trade_feed WHERE TRIM(CAST(ship_date AS TEXT)) = '' ;
