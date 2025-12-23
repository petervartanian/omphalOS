WITH base AS (
  SELECT * FROM { ref('int_trade_by_exporter_country_ship_month') }
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
