WITH base AS (
  SELECT * FROM { ref('int_trade_by_importer_country_hs2_ship_year') }
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
