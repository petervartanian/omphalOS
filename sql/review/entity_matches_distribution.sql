SELECT
  status,
  COUNT(*) AS row_count,
  AVG(score) AS mean_score,
  MIN(score) AS min_score,
  MAX(score) AS max_score
FROM entity_matches
WHERE entity_id = :entity_id
GROUP BY status
ORDER BY status;
