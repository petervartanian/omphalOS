# Orchestration

This folder defines orchestration surfaces that wrap the canonical CLI.

- `jobs.py` and `schedules.py` are a light-weight *registry* pattern useful for cron, CI, or bespoke runners.
- `airflow/` contains example DAGs that call `python -m omphalos ...` directly.

The point is to keep orchestration logic outside the core runtime while still producing
contract-valid run directories.

