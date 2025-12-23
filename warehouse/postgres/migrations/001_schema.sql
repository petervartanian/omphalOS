CREATE SCHEMA IF NOT EXISTS omphalos;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS omphalos.run_manifest (
  run_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  clock_seed TEXT,
  payload_root_sha256 TEXT,
  manifest JSONB
);

CREATE TABLE IF NOT EXISTS omphalos.trade_feed (
  shipment_id TEXT PRIMARY KEY,
  exporter_name TEXT,
  importer_name TEXT,
  exporter_country TEXT,
  importer_country TEXT,
  country TEXT,
  hs_code TEXT,
  hs2 TEXT GENERATED ALWAYS AS (substring(hs_code from 1 for 2)) STORED,
  hs4 TEXT GENERATED ALWAYS AS (substring(hs_code from 1 for 4)) STORED,
  hs6 TEXT GENERATED ALWAYS AS (substring(hs_code from 1 for 6)) STORED,
  value_usd DOUBLE PRECISION,
  ship_date DATE,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id TEXT REFERENCES omphalos.run_manifest(run_id)
);

CREATE INDEX IF NOT EXISTS trade_feed_hs2_idx ON omphalos.trade_feed(hs2);
CREATE INDEX IF NOT EXISTS trade_feed_hs4_idx ON omphalos.trade_feed(hs4);
CREATE INDEX IF NOT EXISTS trade_feed_hs6_idx ON omphalos.trade_feed(hs6);
CREATE INDEX IF NOT EXISTS trade_feed_ship_date_idx ON omphalos.trade_feed(ship_date);
CREATE INDEX IF NOT EXISTS trade_feed_run_idx ON omphalos.trade_feed(run_id);

CREATE TABLE IF NOT EXISTS omphalos.registry (
  entity_id TEXT PRIMARY KEY,
  entity_name TEXT,
  country TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id TEXT REFERENCES omphalos.run_manifest(run_id)
);

CREATE INDEX IF NOT EXISTS registry_country_idx ON omphalos.registry(country);
CREATE INDEX IF NOT EXISTS registry_run_idx ON omphalos.registry(run_id);

CREATE TABLE IF NOT EXISTS omphalos.entity_matches (
  shipment_id TEXT REFERENCES omphalos.trade_feed(shipment_id),
  entity_id TEXT REFERENCES omphalos.registry(entity_id),
  score DOUBLE PRECISION,
  status TEXT,
  explanation TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id TEXT REFERENCES omphalos.run_manifest(run_id),
  PRIMARY KEY (shipment_id, entity_id)
);

CREATE INDEX IF NOT EXISTS entity_matches_status_idx ON omphalos.entity_matches(status);
CREATE INDEX IF NOT EXISTS entity_matches_run_idx ON omphalos.entity_matches(run_id);

CREATE TABLE IF NOT EXISTS omphalos.entity_scores (
  entity_id TEXT REFERENCES omphalos.registry(entity_id),
  entity_name TEXT,
  country TEXT,
  shipment_count INTEGER,
  total_value_usd DOUBLE PRECISION,
  chokepoint_score DOUBLE PRECISION,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id TEXT REFERENCES omphalos.run_manifest(run_id),
  PRIMARY KEY (entity_id, run_id)
);

CREATE INDEX IF NOT EXISTS entity_scores_run_idx ON omphalos.entity_scores(run_id);
CREATE INDEX IF NOT EXISTS entity_scores_score_idx ON omphalos.entity_scores(chokepoint_score);

CREATE TABLE IF NOT EXISTS omphalos.review_queue (
  run_id TEXT REFERENCES omphalos.run_manifest(run_id),
  shipment_id TEXT REFERENCES omphalos.trade_feed(shipment_id),
  entity_id TEXT REFERENCES omphalos.registry(entity_id),
  review_status TEXT NOT NULL,
  severity INTEGER NOT NULL,
  rationale TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, shipment_id, entity_id)
);

CREATE INDEX IF NOT EXISTS review_queue_run_idx ON omphalos.review_queue(run_id);
CREATE INDEX IF NOT EXISTS review_queue_status_idx ON omphalos.review_queue(review_status);
CREATE INDEX IF NOT EXISTS review_queue_severity_idx ON omphalos.review_queue(severity);

CREATE TABLE IF NOT EXISTS omphalos.audit_event (
  audit_id BIGSERIAL PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT,
  action TEXT NOT NULL,
  table_name TEXT NOT NULL,
  row_pk TEXT,
  before_row JSONB,
  after_row JSONB,
  run_id TEXT
);

CREATE INDEX IF NOT EXISTS audit_event_table_idx ON omphalos.audit_event(table_name);
CREATE INDEX IF NOT EXISTS audit_event_run_idx ON omphalos.audit_event(run_id);

CREATE TABLE IF NOT EXISTS omphalos.release_attestation (
  attestation_id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id TEXT REFERENCES omphalos.run_manifest(run_id),
  payload_root_sha256 TEXT NOT NULL,
  policy_bundle_sha256 TEXT,
  attestation JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS release_attestation_run_idx ON omphalos.release_attestation(run_id);
