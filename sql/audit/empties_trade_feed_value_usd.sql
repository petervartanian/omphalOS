SELECT COUNT(*) AS empty_count FROM trade_feed WHERE TRIM(CAST(value_usd AS TEXT)) = '' ;
