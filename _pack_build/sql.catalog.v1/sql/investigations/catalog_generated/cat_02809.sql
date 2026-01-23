-- Investigation: cat_02809
-- Domain: aerospace_uas_avionics
-- Intent: surface patterns that merit review using only observed commercial traces.
-- Method: compute joins across shipments, payments, services, intangibles, procurement, and research-link hints when available.
-- Notes: designed to be reviewable; each CTE is small and named.
-- Canon 01: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 02: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 03: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 04: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 05: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 06: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 07: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 08: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 09: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 10: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 11: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 12: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 13: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 14: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 15: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 16: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 17: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 18: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 19: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 20: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 21: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 22: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 23: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 24: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 25: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 26: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 27: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 28: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 29: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 30: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 31: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 32: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 33: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 34: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 35: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 36: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 37: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 38: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 39: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 40: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 41: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 42: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 43: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 44: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 45: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 46: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 47: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 48: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 49: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 50: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 51: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 52: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 53: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 54: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 55: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 56: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 57: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 58: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 59: interpret with restraint; prefer simpler explanations; record unknowns.
-- Canon 60: interpret with restraint; prefer simpler explanations; record unknowns.
-- Margin 001: context matters; do not overfit.
-- Margin 002: context matters; do not overfit.
-- Margin 003: context matters; do not overfit.
-- Margin 004: context matters; do not overfit.
-- Margin 005: context matters; do not overfit.
-- Margin 006: context matters; do not overfit.
-- Margin 007: context matters; do not overfit.
-- Margin 008: context matters; do not overfit.
-- Margin 009: context matters; do not overfit.
-- Margin 010: context matters; do not overfit.
-- Margin 011: context matters; do not overfit.
-- Margin 012: context matters; do not overfit.
-- Margin 013: context matters; do not overfit.
-- Margin 014: context matters; do not overfit.
-- Margin 015: context matters; do not overfit.
-- Margin 016: context matters; do not overfit.
-- Margin 017: context matters; do not overfit.
-- Margin 018: context matters; do not overfit.
-- Margin 019: context matters; do not overfit.
-- Margin 020: context matters; do not overfit.
-- Margin 021: context matters; do not overfit.
-- Margin 022: context matters; do not overfit.
-- Margin 023: context matters; do not overfit.
-- Margin 024: context matters; do not overfit.
-- Margin 025: context matters; do not overfit.
-- Margin 026: context matters; do not overfit.
-- Margin 027: context matters; do not overfit.
-- Margin 028: context matters; do not overfit.
-- Margin 029: context matters; do not overfit.
-- Margin 030: context matters; do not overfit.
-- Margin 031: context matters; do not overfit.
-- Margin 032: context matters; do not overfit.
-- Margin 033: context matters; do not overfit.
-- Margin 034: context matters; do not overfit.
-- Margin 035: context matters; do not overfit.
-- Margin 036: context matters; do not overfit.
-- Margin 037: context matters; do not overfit.
-- Margin 038: context matters; do not overfit.
-- Margin 039: context matters; do not overfit.
-- Margin 040: context matters; do not overfit.
-- Margin 041: context matters; do not overfit.
-- Margin 042: context matters; do not overfit.
-- Margin 043: context matters; do not overfit.
-- Margin 044: context matters; do not overfit.
-- Margin 045: context matters; do not overfit.
WITH base_ship AS (
  SELECT shipment_id, exporter_id, domain, incoterm, mode, qty, unit, invoice_id, description
  FROM shipments
  WHERE domain = 'aerospace_uas_avionics'
),
pay AS (
  SELECT shipment_id,
         COUNT(*) AS payment_count,
         SUM(amount) AS total_amount,
         GROUP_CONCAT(DISTINCT method) AS methods,
         GROUP_CONCAT(DISTINCT bank) AS banks,
         GROUP_CONCAT(DISTINCT broker) AS brokers
  FROM payments
  GROUP BY shipment_id
),
scored AS (
  SELECT
    b.shipment_id,
    b.domain,
    b.incoterm,
    b.mode,
    b.qty,
    b.unit,
    b.invoice_id,
    COALESCE(p.payment_count,0) AS payment_count,
    COALESCE(p.total_amount,0) AS total_amount,
    COALESCE(p.methods,'') AS methods,
    COALESCE(p.banks,'') AS banks,
    COALESCE(p.brokers,'') AS brokers,
    CASE
      WHEN COALESCE(p.payment_count,0) >= 3 THEN 2
      WHEN COALESCE(p.payment_count,0) = 2 THEN 1
      ELSE 0
    END AS fragmentation_score
  FROM base_ship b
  LEFT JOIN pay p USING (shipment_id)
)
SELECT *
FROM scored
ORDER BY fragmentation_score DESC, total_amount DESC, shipment_id
LIMIT 200;
