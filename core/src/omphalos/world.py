import random, hashlib
from pathlib import Path
from datetime import datetime
from .util import write_json

AOTA_DOMAINS = [
  "chemicals_precursors","machine_tools","aerospace_uas_avionics","maritime_port_equipment",
  "energy_equipment","medical_bio_lab","luxury_dual_use_consumer","services","intangibles",
  "finance_signals","procurement","research_links",
]

def _seed(profile): return int(hashlib.sha256(profile.encode()).hexdigest()[:8], 16)

def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:
        f.write(','.join(header)+'\n')
        for r in rows: f.write(','.join(str(x).replace(',',' ') for x in r)+'\n')

def world_build(profile='national', out_dir='assets/world'):
    out=Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rng=random.Random(_seed(profile))
    meta={"profile":profile,"created_utc":datetime.utcnow().isoformat()+'Z',"domains":AOTA_DOMAINS,
          "recipe":{"entities_base":250000,"shipments_base":600000,"payments_base":500000,"shards":64,"multiplier_hint":100}}
    write_json(out/'meta.json', meta)
    entities=[]
    for i in range(2000):
        entities.append([f"E{i:06d}", rng.choice(["firm","lab","broker","insurer","forwarder"]), rng.randint(1990,2025),
                         f"{rng.randint(10,999)} {rng.choice(['Harbor','Canal','Foundry','Cedar','Quartz'])} {rng.choice(['Rd','St','Ave','Blvd'])}"])
    _write_csv(out/'shards'/'entities_000.csv', ["entity_id","entity_type","year","address"], entities)
    shipments=[]
    for i in range(5000):
        dom=rng.choice(AOTA_DOMAINS[:7])
        shipments.append([f"S{i:07d}", rng.choice(entities)[0], dom, rng.choice(["FOB","CIF","DAP"]), rng.choice(["sea","air","road"]),
                          rng.randint(1,500), rng.choice(["kg","pcs","L"]), f"INV{rng.randint(100000,999999)}", f"{dom} {rng.randint(1,999)}"])
    _write_csv(out/'shards'/'shipments_000.csv', ["shipment_id","exporter_id","domain","incoterm","mode","qty","unit","invoice_id","description"], shipments)
    payments=[]
    for i in range(4000):
        payments.append([f"P{i:07d}", rng.choice(shipments)[0], rng.choice(["wire","cashlike","letter_of_credit"]), rng.randint(1000,200000),
                         rng.choice(["USD","EUR","JPY"]), rng.choice(["bank_A","bank_B","bank_C"]), rng.choice(["broker_X","broker_Y","broker_Z"])])
    _write_csv(out/'shards'/'payments_000.csv', ["payment_id","shipment_id","method","amount","ccy","bank","broker"], payments)
