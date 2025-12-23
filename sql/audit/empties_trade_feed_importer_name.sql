SELECT COUNT(*) AS empty_count FROM trade_feed WHERE TRIM(CAST(importer_name AS TEXT)) = '' ;
