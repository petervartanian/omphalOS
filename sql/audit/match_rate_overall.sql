WITH m AS (
  SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN status = 'MATCH' THEN 1 ELSE 0 END) AS matched_rows
  FROM entity_matches
)
SELECT
  total_rows,
  matched_rows,
  CASE WHEN total_rows = 0 THEN 0.0 ELSE CAST(matched_rows AS DOUBLE) / CAST(total_rows AS DOUBLE) END AS match_rate;
