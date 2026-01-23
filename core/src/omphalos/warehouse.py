import sqlite3

# v1.0 warehouse schema: must accept all columns present in shipped world packs.
SCHEMA = """
CREATE TABLE IF NOT EXISTS entities(
  entity_id TEXT PRIMARY KEY,
  entity_type TEXT,
  year INTEGER,
  address TEXT
);

CREATE TABLE IF NOT EXISTS shipments(
  shipment_id TEXT PRIMARY KEY,
  exporter_id TEXT,
  domain TEXT,
  incoterm TEXT,
  mode TEXT,
  qty REAL,
  unit TEXT,
  invoice_id TEXT,
  description TEXT
);

CREATE TABLE IF NOT EXISTS payments(
  payment_id TEXT PRIMARY KEY,
  shipment_id TEXT,
  method TEXT,
  amount REAL,
  ccy TEXT,
  bank TEXT,
  broker TEXT
);

CREATE TABLE IF NOT EXISTS intangibles(
  int_id TEXT PRIMARY KEY,
  entity_id TEXT,
  kind TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS procurement(
  tender_id TEXT PRIMARY KEY,
  buyer_id TEXT,
  awardee_id TEXT,
  domain TEXT,
  value REAL
);

CREATE TABLE IF NOT EXISTS research(
  link_id TEXT PRIMARY KEY,
  entity_id TEXT,
  topic TEXT,
  score REAL
);

CREATE TABLE IF NOT EXISTS services(
  svc_id TEXT PRIMARY KEY,
  entity_id TEXT,
  kind TEXT,
  hours REAL,
  notes TEXT
);
"""

def connect(path):
    db = sqlite3.connect(str(path))
    db.executescript(SCHEMA)
    return db
