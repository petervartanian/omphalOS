# Warehouse

omphalOS writes a local analytical warehouse for each run and treats the resulting database as an artifact.

The warehouse exists to support three uses:

- deterministic computation of scoring inputs and aggregates
- reproducible review tables used by analysts
- SQL-driven exports suitable for briefing products

## Reference warehouse (SQLite)

Reference runs write:

artifacts/runs/<run_id>/warehouse/warehouse.sqlite

Tables:

trade_feed
  shipment_id, exporter_name, importer_name, country, hs_code, value_usd, ship_date

registry
  entity_id, entity_name, country

entity_matches
  shipment_id, entity_id, score, status, explanation

entity_scores
  entity_id, entity_name, country, shipment_count, total_value_usd, chokepoint_score

The maximal pipeline extends trade_feed with exporter_country and importer_country while preserving the legacy country field.

## dbt project

This directory is a dbt project that defines:

models/staging
  typed staging models with deterministic derived columns

models/intermediate
  joins, deduplication, feature tables, and match expansions

models/marts
  review queues, briefing tables, audit views, and quality metrics

macros
  portable SQL helpers used to keep models compatible across adapters

tests
  model-level tests used by quality gates

## Profiles

warehouse/profiles contains example profiles for:

- sqlite
- duckdb
- postgres

The repository does not embed credentials. Profiles are templates; deployment environments inject secrets using standard mechanisms.

## Outputs as artifacts

dbt execution is expected to export:

- manifest.json
- run_results.json
- compiled SQL

These are written into the run directory under:

artifacts/runs/<run_id>/warehouse/dbt_artifacts/

Quality gates can then evaluate warehouse integrity without re-running transforms.

## Schema DDL

warehouse/db/schema.sql defines a stable schema for warehouse instantiation. Maximal pipelines use this DDL to create tables and indices consistently.
