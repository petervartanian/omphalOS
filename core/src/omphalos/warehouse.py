import sqlite3
SCHEMA="""
CREATE TABLE IF NOT EXISTS entities(entity_id TEXT PRIMARY KEY, entity_type TEXT, year INTEGER, address TEXT);
CREATE TABLE IF NOT EXISTS shipments(shipment_id TEXT PRIMARY KEY, exporter_id TEXT, domain TEXT, incoterm TEXT, mode TEXT, qty REAL, unit TEXT, invoice_id TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS payments(payment_id TEXT PRIMARY KEY, shipment_id TEXT, method TEXT, amount REAL, ccy TEXT, bank TEXT, broker TEXT);
"""
def connect(path):
    db=sqlite3.connect(str(path)); db.executescript(SCHEMA); return db
