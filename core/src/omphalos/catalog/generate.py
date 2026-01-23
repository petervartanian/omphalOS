from pathlib import Path

def generate_leaf(inv_id: str, domain: str) -> str:
    return f"""-- {inv_id}
-- domain: {domain}
WITH base AS (
  SELECT shipment_id, exporter_id, domain, incoterm, mode, qty, unit, invoice_id, description
  FROM shipments
  WHERE domain = '{domain}'
),
pay AS (
  SELECT shipment_id, COUNT(*) AS n_pay, SUM(amount) AS total_amount
  FROM payments
  GROUP BY shipment_id
)
SELECT b.*, COALESCE(p.n_pay,0) AS n_pay, COALESCE(p.total_amount,0) AS total_amount
FROM base b
LEFT JOIN pay p USING (shipment_id)
ORDER BY total_amount DESC, shipment_id
LIMIT 200;
"""

def emit_catalog(out_dir: str | Path, domains: list[str], n_leaf: int = 20000):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(1, n_leaf+1):
        dom = domains[i % len(domains)]
        inv_id = f"cat_{i:05d}"
        (out/f"{inv_id}.sql").write_text(generate_leaf(inv_id, dom), encoding="utf-8")
