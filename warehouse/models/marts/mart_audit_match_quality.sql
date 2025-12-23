WITH m AS (
  SELECT * FROM {{ ref('stg_entity_matches') }}
),
stats AS (
  SELECT
    status,
    COUNT(*) AS row_count,
    AVG(score) AS mean_score,
    MIN(score) AS min_score,
    MAX(score) AS max_score
  FROM m
  GROUP BY status
)
SELECT * FROM stats;
