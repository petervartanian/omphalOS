WITH base AS (
  SELECT * FROM { ref('int_trade_by_hs4_ship_month') }
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY total_value_usd DESC, shipment_count DESC) AS rk
  FROM base
)
SELECT *
FROM ranked
WHERE rk <= 200;
