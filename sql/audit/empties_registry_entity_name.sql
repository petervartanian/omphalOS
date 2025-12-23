SELECT COUNT(*) AS empty_count FROM registry WHERE TRIM(CAST(entity_name AS TEXT)) = '' ;
