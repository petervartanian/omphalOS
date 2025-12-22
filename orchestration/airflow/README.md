# Airflow surface

This folder ships an Airflow integration as an **optional surface**. It is designed to wrap the
same CLI you use locally, so the operational logic does not fork.

## What you get

- `omphalos_nightly_example` - a nightly scheduled run of the example config
- `omphalos_backfill` - a manually triggered backfill DAG (configurable via dagrun conf)

## How to use

1) Install Airflow in your environment (kept out of core dependencies).
2) Point Airflow at this repository as a DAGs folder, or copy `dags/` into your Airflow DAG path.
3) Set environment variables in the worker:

- `OMPHALOS_REPO_ROOT` - where the repo checkout lives on the worker
- `OMPHALOS_OUTPUT_ROOT` - where run directories should be created

The DAGs call:

```bash
python -m omphalos run --config <...> --output-root <...>
```

So the semantics match local runs and the existing `scripts/*.sh` helpers.

