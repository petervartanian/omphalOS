# Warehouse

The reference pipeline writes a local SQLite warehouse inside each run directory:

`<run_dir>/warehouse/warehouse.sqlite`

This folder adds a *real* SQL layer on top of that warehouse:

- a dbt project (`dbt_project.yml`, `models/`, `macros/`)
- documented raw schema (`db/schema.sql`)
- example dbt profiles for SQLite, DuckDB, and Postgres (`profiles/`)

## Why a dbt project lives here

omphalOS treats the run directory as a package. When you add an explicit SQL transform layer
(db t models, tests, macros), you gain:

- a documented contract for what tables exist and how they are derived
- repeatable marts/views for reviewer-facing products
- testable assertions (row-level shape and constraints)

The core omphalOS runtime does **not** invoke dbt by default; this repository ships the
dbt project so the SQL layer can be used in three modes:

1) **SQLite (reference)**: dbt reads `warehouse.sqlite` that the pipeline wrote.
2) **DuckDB (workstation)**: you materialize an equivalent schema into DuckDB, then run dbt.
3) **Postgres (deployment)**: you materialize the schema into Postgres, then run dbt.

## Quickstart (SQLite)

From repo root:

```bash
# Install dbt (choose one adapter; sqlite is not officially supported by dbt-core).
# For the public reference, use DuckDB or Postgres. SQLite is kept as the artifact format.

# Example with DuckDB adapter:
python -m pip install dbt-core dbt-duckdb
```

Then:

```bash
dbt --profiles-dir warehouse/profiles --project-dir warehouse debug
dbt --profiles-dir warehouse/profiles --project-dir warehouse run
dbt --profiles-dir warehouse/profiles --project-dir warehouse test
```

## Profiles

The `warehouse/profiles/` directory includes templates for:

- DuckDB (recommended for the public reference)
- Postgres (recommended for deployed systems)

See `warehouse/profiles/README.md` for the exact knobs.

