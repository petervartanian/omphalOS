CREATE TABLE IF NOT EXISTS trade_feed (
  shipment_id TEXT PRIMARY KEY,
  exporter_name TEXT,
  importer_name TEXT,
  exporter_country TEXT,
  importer_country TEXT,
  country TEXT,
  domain TEXT,
  hs_code TEXT,
  description TEXT,
  incoterm TEXT,
  transport_mode TEXT,
  value_usd DOUBLE,
  ship_date TEXT
);

CREATE TABLE IF NOT EXISTS payments (
  payment_id TEXT PRIMARY KEY,
  shipment_id TEXT,
  payer_name TEXT,
  payee_name TEXT,
  amount_usd DOUBLE,
  currency TEXT,
  method TEXT,
  intermediary_bank TEXT,
  insurer TEXT,
  payment_date TEXT
);

CREATE TABLE IF NOT EXISTS procurement (
  tender_id TEXT PRIMARY KEY,
  buyer_name TEXT,
  supplier_name TEXT,
  domain TEXT,
  description TEXT,
  value_usd DOUBLE,
  notice_date TEXT,
  award_date TEXT
);

CREATE TABLE IF NOT EXISTS services (
  service_id TEXT PRIMARY KEY,
  provider_name TEXT,
  counterparty_name TEXT,
  service_type TEXT,
  description TEXT,
  start_date TEXT,
  end_date TEXT,
  value_usd DOUBLE
);

CREATE TABLE IF NOT EXISTS intangibles (
  intangible_id TEXT PRIMARY KEY,
  owner_name TEXT,
  intangible_type TEXT,
  transfer_mode TEXT,
  description TEXT,
  transfer_date TEXT
);

CREATE TABLE IF NOT EXISTS research_links (
  link_id TEXT PRIMARY KEY,
  entity_name TEXT,
  publication_title TEXT,
  lab_name TEXT,
  link_date TEXT,
  similarity DOUBLE
);

CREATE TABLE IF NOT EXISTS maritime_legs (
  leg_id TEXT PRIMARY KEY,
  shipment_id TEXT,
  from_port TEXT,
  to_port TEXT,
  carrier TEXT,
  vessel_type TEXT,
  transshipment INTEGER,
  depart_date TEXT,
  arrive_date TEXT
);

CREATE TABLE IF NOT EXISTS registry (
  entity_id TEXT PRIMARY KEY,
  entity_name TEXT,
  country TEXT
);

CREATE TABLE IF NOT EXISTS entity_matches (
  shipment_id TEXT,
  entity_id TEXT,
  score DOUBLE,
  status TEXT,
  explanation TEXT
);

CREATE TABLE IF NOT EXISTS entity_scores (
  entity_id TEXT,
  entity_name TEXT,
  country TEXT,
  shipment_count INTEGER,
  total_value_usd DOUBLE,
  chokepoint_score DOUBLE
);
