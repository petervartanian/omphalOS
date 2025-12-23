SELECT
  status,
  explanation,
  COUNT(*) AS row_count
FROM entity_matches
GROUP BY status, explanation
ORDER BY row_count DESC
LIMIT 200;
