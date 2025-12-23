CREATE TABLE IF NOT EXISTS trade_feed (
  shipment_id TEXT PRIMARY KEY,
  exporter_name TEXT NOT NULL,
  importer_name TEXT NOT NULL,
  exporter_country TEXT,
  importer_country TEXT,
  country TEXT,
  hs_code TEXT NOT NULL,
  value_usd REAL NOT NULL,
  ship_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_feed_exporter_name ON trade_feed(exporter_name);
CREATE INDEX IF NOT EXISTS idx_trade_feed_importer_name ON trade_feed(importer_name);
CREATE INDEX IF NOT EXISTS idx_trade_feed_hs_code ON trade_feed(hs_code);
CREATE INDEX IF NOT EXISTS idx_trade_feed_ship_date ON trade_feed(ship_date);

CREATE TABLE IF NOT EXISTS registry (
  entity_id TEXT PRIMARY KEY,
  entity_name TEXT NOT NULL,
  country TEXT
);

CREATE INDEX IF NOT EXISTS idx_registry_entity_name ON registry(entity_name);

CREATE TABLE IF NOT EXISTS entity_matches (
  shipment_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  score REAL NOT NULL,
  status TEXT NOT NULL,
  explanation TEXT NOT NULL,
  PRIMARY KEY (shipment_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_matches_entity ON entity_matches(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_matches_status ON entity_matches(status);

CREATE TABLE IF NOT EXISTS entity_scores (
  entity_id TEXT PRIMARY KEY,
  entity_name TEXT NOT NULL,
  country TEXT,
  shipment_count INTEGER NOT NULL,
  total_value_usd REAL NOT NULL,
  chokepoint_score REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entity_scores_score ON entity_scores(chokepoint_score);

CREATE TABLE IF NOT EXISTS review_queue (
  review_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  entity_id TEXT,
  entity_name TEXT,
  country TEXT,
  severity REAL NOT NULL,
  rationale TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_queue_severity ON review_queue(severity);
