SELECT 'trade_feed' AS table_name, COUNT(*) AS row_count FROM trade_feed
UNION ALL
SELECT 'registry' AS table_name, COUNT(*) AS row_count FROM registry
UNION ALL
SELECT 'entity_matches' AS table_name, COUNT(*) AS row_count FROM entity_matches
UNION ALL
SELECT 'entity_scores' AS table_name, COUNT(*) AS row_count FROM entity_scores;
