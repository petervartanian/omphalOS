WITH t AS (
  SELECT * FROM {{ ref('stg_trade_feed') }}
),
m AS (
  SELECT * FROM {{ ref('stg_entity_matches') }}
),
r AS (
  SELECT * FROM {{ ref('stg_registry') }}
),
counts AS (
  SELECT
    (SELECT COUNT(*) FROM t) AS trade_rows,
    (SELECT COUNT(*) FROM r) AS registry_rows,
    (SELECT COUNT(*) FROM m) AS match_rows,
    (SELECT SUM(CASE WHEN status = 'MATCH' THEN 1 ELSE 0 END) FROM m) AS matched_rows,
    (SELECT SUM(value_usd) FROM t) AS trade_total_value_usd
)
SELECT * FROM counts;
