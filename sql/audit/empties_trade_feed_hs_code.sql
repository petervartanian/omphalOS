SELECT COUNT(*) AS empty_count FROM trade_feed WHERE TRIM(CAST(hs_code AS TEXT)) = '' ;
