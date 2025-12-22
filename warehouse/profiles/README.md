# dbt profiles for omphalOS warehouse

dbt expects a `profiles.yml`. For convenience, this repository ships one here so you can run:

```bash
dbt --profiles-dir warehouse/profiles --project-dir warehouse run
```

## DuckDB (recommended for the public reference)

Set the DuckDB file path if you want it somewhere else:

```bash
export OMPHALOS_DUCKDB_PATH=artifacts/warehouse/warehouse.duckdb
```

Then `dbt run` will materialize views/marts against that DuckDB file.

## Postgres (deployment target)

Set the standard Postgres env vars:

```bash
export PGHOST=localhost
export PGPORT=5432
export PGUSER=omphalos
export PGPASSWORD=omphalos
export PGDATABASE=omphalos
export PGSCHEMA=public
```

Then run dbt as above.

