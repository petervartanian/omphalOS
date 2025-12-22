-- omphalOS reference warehouse schema
--
-- The reference pipeline (src/omphalos/reference/pipeline.py) materializes a local
-- SQLite warehouse inside each run directory at:
--
--   <run_dir>/warehouse/warehouse.sqlite
--
-- This file is *not* executed automatically by the reference pipeline. It exists to:
--
--   1) document the tables the pipeline writes, and
--   2) provide a starting point for teams that want to materialize the same schema
--      outside Python (e.g., DuckDB/Postgres + dbt).
--
-- All example data in this repository is synthetic.

-- Trade shipments (synthetic demo feed)
CREATE TABLE IF NOT EXISTS trade_feed (
  shipment_id   TEXT PRIMARY KEY,
  exporter_name TEXT,
  importer_name TEXT,
  country       TEXT,
  hs_code       TEXT,
  value_usd     REAL,
  ship_date     TEXT
);

-- Reference registry of entities
CREATE TABLE IF NOT EXISTS registry (
  entity_id   TEXT PRIMARY KEY,
  entity_name TEXT,
  country     TEXT
);

-- Match results between shipments and registry entities
CREATE TABLE IF NOT EXISTS entity_matches (
  shipment_id  TEXT,
  entity_id    TEXT,
  score        REAL,
  status       TEXT,
  explanation  TEXT
);

-- Aggregated entity-level scoring (chokepoint scoring in the reference pipeline)
CREATE TABLE IF NOT EXISTS entity_scores (
  entity_id        TEXT,
  entity_name      TEXT,
  country          TEXT,
  shipment_count   INTEGER,
  total_value_usd  REAL,
  chokepoint_score REAL
);

-- Helpful indexes (optional)
CREATE INDEX IF NOT EXISTS idx_trade_feed_country    ON trade_feed(country);
CREATE INDEX IF NOT EXISTS idx_trade_feed_hs_code    ON trade_feed(hs_code);
CREATE INDEX IF NOT EXISTS idx_trade_feed_ship_date  ON trade_feed(ship_date);

CREATE INDEX IF NOT EXISTS idx_registry_country      ON registry(country);
CREATE INDEX IF NOT EXISTS idx_registry_name         ON registry(entity_name);

CREATE INDEX IF NOT EXISTS idx_matches_shipment      ON entity_matches(shipment_id);
CREATE INDEX IF NOT EXISTS idx_matches_entity        ON entity_matches(entity_id);
CREATE INDEX IF NOT EXISTS idx_matches_status        ON entity_matches(status);

CREATE INDEX IF NOT EXISTS idx_scores_country        ON entity_scores(country);
CREATE INDEX IF NOT EXISTS idx_scores_score          ON entity_scores(chokepoint_score);
