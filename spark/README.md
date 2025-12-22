# Spark surface

This folder adds a Spark execution surface for omphalOS.

The design is intentionally simple:

- Spark jobs **produce staging outputs** (typically Parquet) in a run directory.
- dbt (or plain SQL) then builds marts from those staging outputs.
- The omphalOS kernel still owns run identity, manifests, gates, and release bundles.

Nothing in `src/omphalos/` *requires* Spark. This surface exists for teams that need scale.

## Suggested contract

A Spark job should write outputs under:

`<run_dir>/staging/`

For example:

- `<run_dir>/staging/trade_feed/` (Parquet)
- `<run_dir>/staging/registry/` (Parquet)

Downstream, a dbt profile (DuckDB/Postgres) can point sources at those Parquet locations
or load them into tables.

## Included example

- `jobs/ingest_synthetic.py` reads synthetic CSV-like inputs and writes Parquet staging outputs.

