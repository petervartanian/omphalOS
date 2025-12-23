SELECT COUNT(*) AS empty_count FROM trade_feed WHERE TRIM(CAST(exporter_name AS TEXT)) = '' ;
